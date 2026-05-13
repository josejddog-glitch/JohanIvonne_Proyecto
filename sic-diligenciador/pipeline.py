"""Orquesta el procesamiento end-to-end de un caso."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

import auditoria
import claude_runner
import docx_builder
import file_classifier
import pdf_ocr
import resumen_builder
import tipo_detector

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge"
PROMPTS_DIR = ROOT / "prompts"
WORKSPACES_DIR = ROOT / "workspaces"


@dataclass
class CasoEstado:
    caso_id: str
    estado: str = "pendiente"  # pendiente | clasificando | transcribiendo | redactando | listo | error
    iniciado: str = ""
    finalizado: str = ""
    workspace: str = ""
    log: list[str] = field(default_factory=list)
    archivos_salida: list[str] = field(default_factory=list)
    error: str = ""
    clasificacion: dict | None = None
    # Si False, el modelo solo extrae hechos (TITULO + SEGUNDO + TERCERO) sin
    # generar el numeral CUARTO. Útil cuando el abogado solo necesita el
    # resumen del expediente y va a redactar el fallo a mano.
    generar_cuarto: bool = True

    def agregar_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)


def _crear_workspace(caso_id: str) -> Path:
    ws = WORKSPACES_DIR / caso_id
    (ws / "entrada").mkdir(parents=True, exist_ok=True)
    (ws / "entrada" / "transcripciones").mkdir(parents=True, exist_ok=True)
    (ws / "salida").mkdir(parents=True, exist_ok=True)
    return ws


def _guardar_estado(estado: CasoEstado) -> None:
    ws = Path(estado.workspace)
    (ws / "estado.json").write_text(estado.to_json(), encoding="utf-8")


def cargar_estado(caso_id: str) -> CasoEstado | None:
    ws = WORKSPACES_DIR / caso_id
    archivo = ws / "estado.json"
    if not archivo.exists():
        return None
    data = json.loads(archivo.read_text(encoding="utf-8"))
    return CasoEstado(**data)


def crear_caso(
    archivos_subidos: list[tuple[str, bytes]],
    generar_cuarto: bool = True,
) -> CasoEstado:
    """Crea un caso nuevo, guarda los archivos en el workspace y retorna el estado inicial.

    Args:
        archivos_subidos: lista de (nombre, contenido) subidos por el usuario.
        generar_cuarto: si False, el modelo solo genera TITULO+SEGUNDO+TERCERO
            (extracción de hechos), no la CUARTA sección (análisis y fallo).
    """
    caso_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    workspace = _crear_workspace(caso_id)
    entrada = workspace / "entrada"

    for nombre, contenido in archivos_subidos:
        # Sanear el nombre: quitar paths
        nombre_sanitizado = Path(nombre).name
        (entrada / nombre_sanitizado).write_bytes(contenido)

    estado = CasoEstado(
        caso_id=caso_id,
        estado="pendiente",
        iniciado=datetime.now().isoformat(),
        workspace=str(workspace),
        generar_cuarto=generar_cuarto,
    )
    modo = "completo (con CUARTA)" if generar_cuarto else "solo hechos (sin CUARTA)"
    estado.agregar_log(f"Caso creado con {len(archivos_subidos)} archivo(s). Modo: {modo}.")
    _guardar_estado(estado)
    return estado


def procesar_caso(caso_id: str, observaciones: str = "") -> CasoEstado:
    """Pipeline principal. Es bloqueante; el llamador debe correrlo en thread.

    Args:
        caso_id: identificador del caso (carpeta en workspaces/).
        observaciones: notas opcionales del usuario para una regeneración
            (se inyectan en el prompt para que Claude las tenga en cuenta).
    """
    estado = cargar_estado(caso_id)
    if estado is None:
        raise ValueError(f"Caso {caso_id} no existe")

    try:
        workspace = Path(estado.workspace)
        entrada = workspace / "entrada"

        # 1. Clasificación
        estado.estado = "clasificando"
        estado.agregar_log("Clasificando archivos...")
        _guardar_estado(estado)

        archivos = [p for p in entrada.iterdir() if p.is_file()]
        clasificacion = file_classifier.clasificar(archivos)
        estado.clasificacion = clasificacion.to_dict()
        estado.agregar_log(
            f"Expediente principal: {clasificacion.expediente_principal.name if clasificacion.expediente_principal else 'NO DETECTADO'}. "
            f"Anexos PDF: {len(clasificacion.anexos_pdf)}. "
            f"Anexos DOCX: {len(clasificacion.anexos_doc)}. "
            f"Audios: {len(clasificacion.audios)}."
        )
        _guardar_estado(estado)

        # 2a. OCR previo de PDFs (expediente principal y anexos PDF) si Tesseract está disponible.
        ocr_dir = entrada / "ocr"
        if pdf_ocr.disponible():
            estado.agregar_log("OCR previo de PDFs con Tesseract+Poppler...")
            _guardar_estado(estado)
            pdfs_a_ocr: list[Path] = []
            if clasificacion.expediente_principal:
                pdfs_a_ocr.append(clasificacion.expediente_principal)
            pdfs_a_ocr.extend(clasificacion.anexos_pdf)
            for pdf in pdfs_a_ocr:
                t0 = time.time()
                try:
                    out = pdf_ocr.ocr_pdf_a_txt(pdf, ocr_dir)
                    estado.agregar_log(
                        f"  OCR: {pdf.name} -> {out.name} ({time.time() - t0:.1f}s)"
                    )
                except Exception as e:
                    estado.agregar_log(f"  OCR FALLÓ en {pdf.name}: {e} (Claude leerá vía visión)")
                _guardar_estado(estado)
        else:
            estado.agregar_log("OCR Tesseract no disponible — Claude leerá los PDFs vía visión.")

        # 2b. Transcripción de audios (si hay) - paralelizada y con caché
        if clasificacion.audios:
            estado.estado = "transcribiendo"
            estado.agregar_log(
                f"Transcribiendo {len(clasificacion.audios)} audio(s) con Whisper "
                f"(modelo {os.environ.get('SIC_WHISPER_MODEL', 'small')}, hasta 2 en paralelo, caché activo)..."
            )
            _guardar_estado(estado)
            import audio_transcribe  # import diferido para que no falle si no hay audios

            transcripciones_dir = entrada / "transcripciones"
            t0 = time.time()
            rutas = audio_transcribe.transcribir_varios(
                clasificacion.audios, transcripciones_dir, max_workers=2
            )
            elapsed = time.time() - t0
            for audio, ruta_txt in zip(clasificacion.audios, rutas):
                estado.agregar_log(f"  Transcrito: {audio.name} -> {ruta_txt.name}")
            estado.agregar_log(f"Transcripción total: {elapsed:.1f}s para {len(rutas)} audio(s).")
            _guardar_estado(estado)

        # 3. Renderizar prompt
        estado.estado = "redactando"
        estado.agregar_log("Construyendo prompt y llamando a Claude Code...")
        _guardar_estado(estado)

        prompt_largo = _renderizar_prompt(
            workspace,
            clasificacion,
            observaciones=observaciones,
            generar_cuarto=estado.generar_cuarto,
        )
        prompt_path = workspace / "prompt_usado.md"
        prompt_path.write_text(prompt_largo, encoding="utf-8")

        # 4. Invocar Claude. Como el prompt completo (con bloques inline) supera el
        #    límite de línea de comandos en Windows (~8KB), lo escribimos a archivo
        #    y le pasamos a Claude un prompt corto que le dice que lea ese archivo.
        prompt_corto = (
            f"Lee el archivo `{prompt_path}` completo. Sigue EXACTAMENTE las "
            f"instrucciones que contiene. Tu respuesta debe ser SOLO el objeto JSON "
            f"que se te pide al final del archivo, sin texto adicional."
        )
        t0 = time.time()
        rc, stdout, stderr = claude_runner.ejecutar(prompt_corto, cwd=ROOT, timeout=1800)
        elapsed = time.time() - t0
        estado.agregar_log(f"Claude terminó en {elapsed:.1f}s (rc={rc}).")
        (workspace / "claude_stdout.log").write_text(stdout or "", encoding="utf-8")
        (workspace / "claude_stderr.log").write_text(stderr or "", encoding="utf-8")

        # 5. Parsear JSON y construir archivos finales con Python
        salida_dir = workspace / "salida"
        salida_dir.mkdir(parents=True, exist_ok=True)
        datos = _parsear_json_respuesta(stdout)
        if not isinstance(datos, dict):
            raise RuntimeError(
                "La respuesta de Claude no es un JSON válido. Revisa claude_stdout.log."
            )
        (salida_dir / "respuesta_claude.json").write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        docx_builder.construir(
            plantilla_path=KNOWLEDGE_DIR / "plantilla.docx",
            salida_path=salida_dir / "resolucion_diligenciada.docx",
            datos=datos,
        )
        resumen_builder.construir(
            salida_path=salida_dir / "resumen.md",
            caso_id=caso_id,
            datos=datos,
        )

        esperados = ["resolucion_diligenciada.docx", "resumen.md"]
        faltantes = [n for n in esperados if not (salida_dir / n).exists()]
        if faltantes:
            raise RuntimeError(f"Builders no produjeron: {faltantes}")
        estado.archivos_salida = [str(salida_dir / n) for n in esperados]
        estado.estado = "listo"
        estado.finalizado = datetime.now().isoformat()
        estado.agregar_log("Caso terminado correctamente.")
        _guardar_estado(estado)
        try:
            auditoria.registrar(estado)
        except Exception:
            logger.exception("No se pudo registrar en auditoría")
        return estado

    except Exception as e:
        logger.exception("Fallo procesando caso %s", caso_id)
        estado.estado = "error"
        estado.error = str(e)
        estado.agregar_log(f"ERROR: {e}")
        estado.finalizado = datetime.now().isoformat()
        _guardar_estado(estado)
        try:
            auditoria.registrar(estado)
        except Exception:
            logger.exception("No se pudo registrar en auditoría")
        raise


def _parsear_json_respuesta(stdout: str) -> dict | None:
    """Extrae el JSON de respuesta de Claude.

    Cuando el CLI se invoca con `--output-format json`, stdout viene como un
    sobre: {type:"result", result:"<texto Claude>", session_id:..., ...}.
    Aquí desempaquetamos el sobre y parseamos el `result` que contiene el JSON
    real generado por Claude.

    Tolera el caso legacy (sin sobre) buscando el primer/último `{}`.
    """
    if not stdout:
        return None
    txt = stdout.strip()

    # Caso 1: sobre de --output-format json
    try:
        envelope = json.loads(txt)
        if isinstance(envelope, dict) and "result" in envelope:
            inner = envelope.get("result", "")
            if isinstance(inner, str):
                return _parsear_inner_json(inner)
            if isinstance(inner, dict):
                return inner
    except json.JSONDecodeError:
        pass

    # Caso 2: legacy / texto plano sin sobre — intentar parsear directo
    return _parsear_inner_json(txt)


def _parsear_inner_json(txt: str) -> dict | None:
    """Parsea el JSON real generado por Claude. Tolera fences markdown
    y texto pre/post accidental."""
    if not txt:
        return None
    txt = txt.strip()
    # quitar fences de markdown si las hay
    if txt.startswith("```"):
        first_newline = txt.find("\n")
        if first_newline != -1:
            txt = txt[first_newline + 1:]
        if txt.endswith("```"):
            txt = txt[:-3]
    txt = txt.strip()
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        # buscar el primer { ... }
        ini = txt.find("{")
        fin = txt.rfind("}")
        if ini != -1 and fin > ini:
            try:
                parsed = json.loads(txt[ini:fin + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _renderizar_prompt(
    workspace: Path,
    clasificacion: file_classifier.ClasificacionCaso,
    observaciones: str = "",
    generar_cuarto: bool = True,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    plantilla_caso = env.get_template("caso.md.j2")

    transcripciones_dir = workspace / "entrada" / "transcripciones"
    transcripciones = sorted(transcripciones_dir.glob("*.txt")) if transcripciones_dir.exists() else []

    ocr_dir = workspace / "entrada" / "ocr"
    ocr_textos = sorted(ocr_dir.glob("*_ocr.txt")) if ocr_dir.exists() else []

    # Pre-detectar tipologías leyendo el OCR + transcripciones para sesgar al modelo
    texto_para_detectar = ""
    for p in ocr_textos:
        try:
            texto_para_detectar += "\n" + p.read_text(encoding="utf-8")
        except Exception:
            pass
    for p in transcripciones:
        try:
            texto_para_detectar += "\n" + p.read_text(encoding="utf-8")
        except Exception:
            pass
    tipologias_candidatas = tipo_detector.detectar(texto_para_detectar, top_n=3)
    bloques_inline = tipo_detector.cargar_bloques_aplicables(tipologias_candidatas)

    # Cargar aprendizajes permanentes del abogado (si los hay)
    learnings_path = KNOWLEDGE_DIR / "learnings.md"
    learnings_txt = ""
    if learnings_path.exists():
        raw = learnings_path.read_text(encoding="utf-8")
        # Filtrar líneas de instrucción (comentarios HTML y headers); incluir solo
        # las líneas con contenido real ('-' al inicio o texto plano).
        lineas_utiles = []
        for linea in raw.splitlines():
            s = linea.strip()
            if not s or s.startswith("<!--") or s.startswith("#") or s.startswith(">"):
                continue
            lineas_utiles.append(linea)
        learnings_txt = "\n".join(lineas_utiles).strip()

    contexto = {
        "caso_id": workspace.name,
        "workspace": str(workspace),
        "knowledge_dir": str(KNOWLEDGE_DIR),
        "expediente": str(clasificacion.expediente_principal) if clasificacion.expediente_principal else None,
        "anexos_pdf": [str(p) for p in clasificacion.anexos_pdf],
        "anexos_doc": [str(p) for p in clasificacion.anexos_doc],
        "audios": [str(p) for p in clasificacion.audios],
        "transcripciones": [str(p) for p in transcripciones],
        "ocr_textos": [str(p) for p in ocr_textos],
        "salida_dir": str(workspace / "salida"),
        "plantilla_path": str(KNOWLEDGE_DIR / "plantilla.docx"),
        "manual_path": str(KNOWLEDGE_DIR / "manual_sic.docx"),
        "ejemplos_dir": str(KNOWLEDGE_DIR / "ejemplos"),
        "bloques_dir": str(KNOWLEDGE_DIR / "bloques"),
        "frases_ancla_path": str(KNOWLEDGE_DIR / "frases_ancla.md"),
        "tipologias_path": str(KNOWLEDGE_DIR / "tipologias.md"),
        "reglas_extraidas_path": str(KNOWLEDGE_DIR / "reglas_extraidas.md"),
        "observaciones": observaciones.strip() if observaciones else "",
        "tipologias_candidatas": [
            {"nombre": t.nombre, "score": t.score, "matches": t.matches, "bloques": t.bloques}
            for t in tipologias_candidatas
        ],
        "bloques_inline": bloques_inline,
        "learnings": learnings_txt,
        "generar_cuarto": generar_cuarto,
    }
    return plantilla_caso.render(**contexto)
