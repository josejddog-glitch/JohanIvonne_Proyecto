"""Gestiona el procesamiento por lotes (batch) de varios casos en un único ZIP.

Cada carpeta de primer nivel del ZIP se trata como un caso independiente:
los archivos de adentro se pasan a `pipeline.crear_caso()` y luego se encolan.
Un único worker thread procesa los casos secuencialmente (uno a la vez),
respetando el rate limit de Claude y evitando corrupción de Tesseract / audit.csv.

Estructura en disco:
    workspaces/
    ├── batches/
    │   └── <batch_id>/estado_batch.json    # lista de caso_ids del batch
    └── <caso_id>/                          # workspace estándar (uno por caso)
"""
from __future__ import annotations

import io
import json
import logging
import os
import queue
import threading
import uuid
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import pipeline

try:
    import psutil  # opcional, usado para matar subprocesos claude colgados
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
WORKSPACES_DIR = ROOT / "workspaces"
BATCHES_DIR = WORKSPACES_DIR / "batches"

# Tipos de archivo aceptados como insumo de un caso (alineado con file_classifier).
EXTENSIONES_VALIDAS = {
    ".pdf", ".docx", ".doc",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
}


@dataclass
class BatchEstado:
    batch_id: str
    iniciado: str = ""           # timestamp ISO de cuando se confirmó el inicio (vacío si todavía en preview)
    confirmado: bool = False     # True una vez que el usuario confirmó el modal y se encoló
    finalizado: str = ""
    generar_cuarto: bool = True
    caso_ids: list[str] = field(default_factory=list)
    # Mapeo caso_id -> nombre original de la carpeta del ZIP (para mostrar en la UI).
    nombres: dict[str, str] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)
    creado: str = ""             # cuando se creó el preview (siempre se setea)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Persistencia ----------

def _path_estado_batch(batch_id: str) -> Path:
    return BATCHES_DIR / batch_id / "estado_batch.json"


def _guardar_batch(estado: BatchEstado) -> None:
    p = _path_estado_batch(estado.batch_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(estado.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_batch(batch_id: str) -> BatchEstado | None:
    p = _path_estado_batch(batch_id)
    if not p.exists():
        return None
    try:
        return BatchEstado(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        logger.exception("No se pudo leer estado_batch.json de %s", batch_id)
        return None


# ---------- Cola global + worker único ----------

_cola: queue.Queue[str] = queue.Queue()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def _worker_loop() -> None:
    """Procesa casos en orden FIFO. Si uno falla, sigue con el siguiente."""
    logger.info("Worker batch iniciado. Esperando casos en la cola...")
    while True:
        try:
            caso_id = _cola.get()
        except Exception:
            logger.exception("Worker: error tomando de la cola (sale del loop)")
            return
        logger.info("Worker: tomó caso %s de la cola (cola restante: %d)", caso_id, _cola.qsize())
        try:
            pipeline.procesar_caso(caso_id)
        except Exception:
            logger.exception("Worker: caso %s falló (sigue con el siguiente)", caso_id)
        finally:
            _cola.task_done()
            logger.info("Worker: caso %s liberado, esperando siguiente.", caso_id)


def asegurar_worker() -> None:
    """Arranca el worker thread si no existe. Idempotente y thread-safe."""
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="batch-worker", daemon=True)
            _worker.start()
            logger.info("Worker batch creado y arrancado. Casos en cola: %d", _cola.qsize())
        else:
            logger.info("Worker batch ya estaba vivo. Casos en cola: %d", _cola.qsize())


def encolar(caso_id: str) -> None:
    """Marca el caso como 'en_cola' y lo agrega a la cola global."""
    pipeline.encolar_caso(caso_id)
    _cola.put(caso_id)
    logger.info("Caso %s encolado. Cola actual: %d", caso_id, _cola.qsize())


# ---------- Recuperación post-reinicio ----------

def recuperar_pendientes() -> int:
    """Al arrancar la app, busca casos huérfanos en `workspaces/` y los maneja
    según su estado:

    - **`en_cola`**: el caso ya fue confirmado y estaba esperando turno del
      worker → se re-encola.
    - **`pendiente`**: el caso fue creado en un preview pero el usuario no
      confirmó. NO se re-encola automáticamente para no procesar lotes
      cancelados/abandonados. Si el usuario quiere retomarlo, debe ir al
      historial de batches y darle "iniciar".
    - **`clasificando` / `transcribiendo` / `redactando`**: el caso ya estaba
      a medio procesar cuando se interrumpió. Re-encolarlo significa volver
      a invocar Claude (que puede tardar 30 min o colgarse) y bloquear el
      worker. Es más seguro marcarlos como `error` para que el usuario decida
      si re-procesarlos manualmente desde `/caso/<id>` (botón Regenerar).

    Retorna la cantidad de casos efectivamente re-encolados.
    """
    if not WORKSPACES_DIR.exists():
        return 0
    n_reencolados = 0
    n_marcados_error = 0
    estados_seguros_a_reencolar = {"en_cola"}
    estados_a_medio_procesar = {"clasificando", "transcribiendo", "redactando"}
    for ws in WORKSPACES_DIR.iterdir():
        if not ws.is_dir() or ws.name == "batches":
            continue
        estado_json = ws / "estado.json"
        if not estado_json.exists():
            continue
        try:
            data = json.loads(estado_json.read_text(encoding="utf-8"))
            estado_actual = data.get("estado")
            caso_id = data.get("caso_id") or ws.name

            if estado_actual in estados_seguros_a_reencolar:
                _cola.put(caso_id)
                n_reencolados += 1
                logger.info("Re-encolado caso huérfano: %s (estaba en %s)", caso_id, estado_actual)

            elif estado_actual in estados_a_medio_procesar:
                # Marcar como error: estaba a medio procesar y reiniciar
                # podría colgar el worker (típico cuando Claude no respondió).
                data["estado"] = "error"
                data["error"] = (
                    f"Procesamiento interrumpido por reinicio del servidor (estaba en '{estado_actual}'). "
                    "Re-procesar manualmente desde la página del caso si lo necesitas."
                )
                data["finalizado"] = datetime.now().isoformat()
                log = data.get("log") or []
                log.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Marcado como error tras reinicio (estaba en '{estado_actual}', "
                    "no se re-procesa automáticamente para no bloquear el worker)."
                )
                data["log"] = log
                estado_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                n_marcados_error += 1
                logger.info(
                    "Caso %s marcado como error (estaba en %s, no se re-procesa)",
                    caso_id, estado_actual,
                )
        except Exception:
            logger.exception("Error procesando estado.json de %s", ws.name)
            continue

    if n_marcados_error > 0:
        logger.warning(
            "%d caso(s) marcados como error porque estaban a medio procesar al reiniciar. "
            "Revisarlos manualmente en /casos.",
            n_marcados_error,
        )
    if n_reencolados > 0:
        asegurar_worker()
    return n_reencolados


# ---------- Descompresión y creación de casos ----------

def _validar_zip_entry(name: str) -> bool:
    """Rechaza paths peligrosos (traversal con `..` o paths absolutos)."""
    if not name or name.startswith("/") or name.startswith("\\"):
        return False
    if ".." in Path(name).parts:
        return False
    if len(name) > 500:
        return False
    return True


def _agrupar_archivos_por_carpeta(zf: zipfile.ZipFile) -> dict[str, list[tuple[str, bytes]]]:
    """Recorre el ZIP y agrupa archivos por la carpeta de primer nivel.

    Retorna: {nombre_carpeta: [(nombre_archivo, contenido_bytes), ...]}

    Las entries que están en la raíz (sin carpeta) se agrupan bajo el key
    especial `__raiz__` y se reportan como un solo caso "sin agrupar".
    """
    grupos: dict[str, list[tuple[str, bytes]]] = {}
    for entry in zf.infolist():
        if entry.is_dir():
            continue
        if not _validar_zip_entry(entry.filename):
            logger.warning("ZIP entry rechazada por seguridad: %r", entry.filename)
            continue
        # Normalizar separadores y partir
        partes = Path(entry.filename.replace("\\", "/")).parts
        if not partes:
            continue
        nombre_archivo = Path(partes[-1]).name
        # Filtrar extensiones no útiles (silenciosamente)
        ext = Path(nombre_archivo).suffix.lower()
        if ext not in EXTENSIONES_VALIDAS:
            continue
        # Identificar grupo: primer componente del path si hay >=2 partes
        if len(partes) >= 2:
            grupo = partes[0]
        else:
            grupo = "__raiz__"
        # Leer contenido
        try:
            contenido = zf.read(entry)
        except Exception as e:
            logger.warning("No se pudo leer %s del ZIP: %s", entry.filename, e)
            continue
        grupos.setdefault(grupo, []).append((nombre_archivo, contenido))
    return grupos


def crear_batch_preview(zip_bytes: bytes, generar_cuarto: bool = True) -> BatchEstado:
    """Descomprime el ZIP y crea un caso por carpeta de primer nivel, pero
    NO los encola ni arranca el worker. Los casos quedan en estado
    `pendiente` esperando confirmación del usuario via el modal.

    Para confirmar e iniciar el procesamiento real, llamá `iniciar_batch()`.
    Para descartar el lote, llamá `cancelar_batch()`.

    Lanza ValueError si el ZIP es inválido o no contiene archivos útiles.
    """
    batch_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + "batch-" + uuid.uuid4().hex[:6]
    estado = BatchEstado(
        batch_id=batch_id,
        creado=datetime.now().isoformat(),
        generar_cuarto=generar_cuarto,
        confirmado=False,
    )

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except zipfile.BadZipFile as e:
        raise ValueError(f"Archivo ZIP inválido: {e}") from e

    with zf:
        grupos = _agrupar_archivos_por_carpeta(zf)

    if not grupos:
        raise ValueError(
            "El ZIP no contiene archivos útiles (PDF, DOCX o audio). "
            "Cada carpeta debe traer al menos un expediente."
        )

    # Advertir si hay archivos sueltos en la raíz
    if "__raiz__" in grupos and len(grupos) > 1:
        estado.advertencias.append(
            f"Se ignoraron {len(grupos['__raiz__'])} archivo(s) sueltos en la raíz del ZIP. "
            "Pon cada caso dentro de su propia carpeta."
        )
        del grupos["__raiz__"]
    elif list(grupos.keys()) == ["__raiz__"]:
        # ZIP plano: tratar todo como un solo caso (comportamiento conservador)
        estado.advertencias.append(
            "El ZIP no tiene carpetas — se procesó como un único caso. "
            "Para procesar varios casos, ponlos en carpetas separadas dentro del ZIP."
        )
        grupos = {"caso_unico": grupos["__raiz__"]}

    # Crear un caso por cada grupo (ordenado para reproducibilidad).
    # Los casos quedan en estado `pendiente` y NO se encolan todavía.
    for nombre_carpeta in sorted(grupos.keys()):
        archivos = grupos[nombre_carpeta]
        if not archivos:
            continue
        caso_estado = pipeline.crear_caso(archivos, generar_cuarto=generar_cuarto)
        estado.caso_ids.append(caso_estado.caso_id)
        estado.nombres[caso_estado.caso_id] = nombre_carpeta

    if not estado.caso_ids:
        raise ValueError("Ninguna carpeta tenía archivos útiles.")

    _guardar_batch(estado)
    return estado


def iniciar_batch(batch_id: str) -> BatchEstado | None:
    """Marca el batch como confirmado y encola TODOS sus casos para que el
    worker los procese. Llamar después de que el usuario confirma el modal.

    Es idempotente: si ya fue iniciado, no encola dos veces.
    """
    estado = cargar_batch(batch_id)
    if estado is None:
        return None
    if estado.confirmado:
        logger.info("Batch %s ya fue iniciado antes, ignorando.", batch_id)
        return estado

    estado.confirmado = True
    estado.iniciado = datetime.now().isoformat()
    _guardar_batch(estado)

    # Encolar todos los casos del batch (cambia su estado de 'pendiente' a 'en_cola')
    for caso_id in estado.caso_ids:
        encolar(caso_id)
    asegurar_worker()
    logger.info("Batch %s iniciado con %d caso(s).", batch_id, len(estado.caso_ids))
    return estado


def cancelar_batch(batch_id: str) -> BatchEstado | None:
    """Cancela un batch que está en estado de preview (no confirmado). Marca
    todos sus casos como `error` con motivo "Cancelado antes de iniciar".

    Si el batch ya fue confirmado e iniciado, NO se permite cancelar desde
    aquí (usar la cancelación individual de cada caso).
    """
    estado = cargar_batch(batch_id)
    if estado is None:
        return None
    if estado.confirmado:
        logger.warning("Intento de cancelar batch ya iniciado: %s", batch_id)
        return estado

    estado.finalizado = datetime.now().isoformat()
    _guardar_batch(estado)

    # Marcar cada caso como error
    for caso_id in estado.caso_ids:
        caso_estado = pipeline.cargar_estado(caso_id)
        if caso_estado is None:
            continue
        if caso_estado.estado == "pendiente":
            caso_estado.estado = "error"
            caso_estado.error = "Cancelado antes de iniciar (usuario rechazó el modal de confirmación)."
            caso_estado.finalizado = datetime.now().isoformat()
            caso_estado.agregar_log("Caso cancelado antes de iniciar.")
            pipeline._guardar_estado(caso_estado)
    logger.info("Batch %s cancelado (%d caso(s) marcados como error).", batch_id, len(estado.caso_ids))
    return estado


# Mantenemos el nombre legacy por compatibilidad con tests/calibrar — pero
# ahora hace el flow completo (crea y arranca, sin modal).
def crear_batch_desde_zip(zip_bytes: bytes, generar_cuarto: bool = True) -> BatchEstado:
    """Crea el batch Y lo inicia inmediatamente (sin modal). Solo para uso
    programático/tests. La UI usa crear_batch_preview + iniciar_batch.
    """
    estado = crear_batch_preview(zip_bytes, generar_cuarto)
    iniciar_batch(estado.batch_id)
    return cargar_batch(estado.batch_id) or estado


# ---------- Vista agregada para la UI ----------

def _vaciar_cola() -> int:
    """Quita TODOS los items pendientes de la cola sin procesarlos.
    Retorna cuántos items se quitaron.
    """
    n = 0
    while True:
        try:
            _cola.get_nowait()
            _cola.task_done()
            n += 1
        except queue.Empty:
            break
    return n


def _matar_subprocesos_claude() -> int:
    """Mata los procesos `claude` y `claude.cmd` que son hijos del proceso
    Python actual (Flask). NO toca claude.exe de otras sesiones del usuario
    (por ejemplo, una sesión de Claude Code separada en otra terminal).

    Requiere psutil. Retorna la cantidad de procesos matados.
    Si psutil no está instalado, retorna -1.
    """
    if not PSUTIL_AVAILABLE:
        return -1
    matados = 0
    try:
        propio = psutil.Process(os.getpid())
        for child in propio.children(recursive=True):
            try:
                nombre = (child.name() or "").lower()
                if "claude" in nombre or "node" in nombre:
                    child.kill()
                    matados += 1
                    logger.info("Matado subproceso: PID=%d name=%s", child.pid, nombre)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.exception("Error matando subprocesos claude: %s", e)
    return matados


def detener_procesos() -> dict:
    """Detiene todo procesamiento en curso de forma segura:

    1. **Vacía la cola** del worker (los casos `en_cola` se descartan).
    2. **Mata subprocesos `claude` hijos** del proceso Flask (libera el
       caso que estuviera trabado esperando respuesta de Claude).
    3. **Marca todos los casos no terminales como `error`** con motivo
       "Detenido por el usuario".

    El worker thread queda vivo y esperando un nuevo caso (no se mata).

    Retorna stats: cantidad de items quitados de la cola, claude matados,
    casos marcados como error.
    """
    n_cola = _vaciar_cola()
    n_claude = _matar_subprocesos_claude()

    # Marcar casos no terminales como error
    estados_no_terminales = {
        "en_cola", "pendiente",
        "clasificando", "transcribiendo", "redactando",
    }
    n_marcados = 0
    if WORKSPACES_DIR.exists():
        for ws in WORKSPACES_DIR.iterdir():
            if not ws.is_dir() or ws.name == "batches":
                continue
            estado_json = ws / "estado.json"
            if not estado_json.exists():
                continue
            try:
                data = json.loads(estado_json.read_text(encoding="utf-8"))
                prev = data.get("estado")
                if prev not in estados_no_terminales:
                    continue
                data["estado"] = "error"
                data["error"] = f"Detenido por el usuario (estaba en {prev!r})."
                data["finalizado"] = datetime.now().isoformat()
                log = data.get("log") or []
                log.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    "Detenido por el usuario via el botón de la interfaz."
                )
                data["log"] = log
                estado_json.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                n_marcados += 1
            except Exception:
                logger.exception("Error marcando %s como error", ws.name)
                continue

    resultado = {
        "cola_vaciada": n_cola,
        "subprocesos_claude_matados": n_claude,
        "casos_marcados_error": n_marcados,
        "psutil_disponible": PSUTIL_AVAILABLE,
    }
    logger.warning("DETENER PROCESOS: %s", resultado)
    return resultado


def _duracion_seg(iniciado: str, finalizado: str = "") -> float | None:
    """Calcula segundos entre `iniciado` y `finalizado` (ambos ISO).
    Si `finalizado` está vacío, usa `datetime.now()` (caso en curso).
    Si `iniciado` está vacío o no parseable, retorna None.
    """
    if not iniciado:
        return None
    try:
        t0 = datetime.fromisoformat(iniciado)
        t1 = datetime.fromisoformat(finalizado) if finalizado else datetime.now()
        return max(0.0, (t1 - t0).total_seconds())
    except Exception:
        return None


def listar_batches(limite: int = 50) -> list[dict]:
    """Retorna la lista de batches ordenados del más reciente al más antiguo.
    Incluye contadores agregados (listos, en cola, error) y duración total
    del lote (desde el inicio hasta el último caso terminado).
    """
    if not BATCHES_DIR.exists():
        return []
    salida: list[dict] = []
    # Carpetas ordenadas inversamente (el nombre empieza con timestamp)
    carpetas = sorted(
        [p for p in BATCHES_DIR.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for carpeta in carpetas[:limite]:
        batch_estado = cargar_batch(carpeta.name)
        if batch_estado is None:
            continue
        contadores = {"en_cola": 0, "procesando": 0, "listo": 0, "error": 0}
        suma_seg = 0.0
        n_terminados = 0
        for caso_id in batch_estado.caso_ids:
            caso_estado = pipeline.cargar_estado(caso_id)
            if caso_estado is None:
                continue
            if caso_estado.estado == "listo":
                contadores["listo"] += 1
            elif caso_estado.estado == "error":
                contadores["error"] += 1
            elif caso_estado.estado == "en_cola":
                contadores["en_cola"] += 1
            else:
                contadores["procesando"] += 1
            # Acumular duración de los casos terminados
            if caso_estado.estado in {"listo", "error"} and caso_estado.iniciado and caso_estado.finalizado:
                d = _duracion_seg(caso_estado.iniciado, caso_estado.finalizado)
                if d is not None:
                    suma_seg += d
                    n_terminados += 1
        # Duración total del lote (wall-clock): inicio del batch hasta finalizado o ahora
        duracion_total = _duracion_seg(batch_estado.iniciado, batch_estado.finalizado)
        # Promedio por caso terminado
        promedio_seg = (suma_seg / n_terminados) if n_terminados > 0 else None
        salida.append({
            "batch_id": batch_estado.batch_id,
            "iniciado": batch_estado.iniciado,
            "finalizado": batch_estado.finalizado,
            "generar_cuarto": batch_estado.generar_cuarto,
            "total": len(batch_estado.caso_ids),
            "contadores": contadores,
            "duracion_total_seg": duracion_total,
            "duracion_promedio_seg": promedio_seg,
            "suma_duraciones_seg": suma_seg if n_terminados > 0 else None,
        })
    return salida


def estado_completo_batch(batch_id: str) -> dict | None:
    """Combina el BatchEstado con el estado actual de cada caso (leyendo sus
    estado.json). Pensado para el endpoint /batch/<id>/status.

    Retorna estructura serializable a JSON con totales agregados.
    """
    batch_estado = cargar_batch(batch_id)
    if batch_estado is None:
        return None

    casos: list[dict] = []
    contadores = {"en_cola": 0, "procesando": 0, "listo": 0, "error": 0}
    for caso_id in batch_estado.caso_ids:
        caso_estado = pipeline.cargar_estado(caso_id)
        if caso_estado is None:
            continue
        # Categorizar
        if caso_estado.estado == "listo":
            contadores["listo"] += 1
        elif caso_estado.estado == "error":
            contadores["error"] += 1
        elif caso_estado.estado == "en_cola":
            contadores["en_cola"] += 1
        else:
            contadores["procesando"] += 1
        # Datos para la fila de la tabla
        clas = caso_estado.clasificacion or {}
        n_archivos = (
            (1 if clas.get("expediente_principal") else 0)
            + len(clas.get("anexos_pdf", []) or [])
            + len(clas.get("anexos_doc", []) or [])
            + len(clas.get("audios", []) or [])
        )
        # Si todavía no se clasificó, contar archivos en entrada/
        if n_archivos == 0 and caso_estado.workspace:
            entrada = Path(caso_estado.workspace) / "entrada"
            if entrada.exists():
                n_archivos = sum(
                    1 for p in entrada.iterdir()
                    if p.is_file() and p.suffix.lower() in EXTENSIONES_VALIDAS
                )
        # Duración: si terminó, fin - inicio; si está en curso, ahora - inicio.
        # Para casos en_cola/pendiente que no han empezado, no hay duración.
        if caso_estado.estado in {"en_cola", "pendiente"}:
            duracion_seg = None
        else:
            duracion_seg = _duracion_seg(caso_estado.iniciado, caso_estado.finalizado)
        casos.append({
            "caso_id": caso_estado.caso_id,
            "nombre": batch_estado.nombres.get(caso_id, caso_id),
            "estado": caso_estado.estado,
            "iniciado": caso_estado.iniciado,
            "finalizado": caso_estado.finalizado,
            "duracion_seg": duracion_seg,
            "n_archivos": n_archivos,
            "error": caso_estado.error or "",
            "archivos_salida": [Path(p).name for p in (caso_estado.archivos_salida or [])],
            "ultimo_log": (caso_estado.log[-1] if caso_estado.log else ""),
        })

    # Si todos los casos están en estado terminal, marcar el batch como finalizado
    total = len(batch_estado.caso_ids)
    if total > 0 and (contadores["listo"] + contadores["error"]) == total and not batch_estado.finalizado:
        batch_estado.finalizado = datetime.now().isoformat()
        _guardar_batch(batch_estado)

    return {
        "batch_id": batch_estado.batch_id,
        "iniciado": batch_estado.iniciado,
        "finalizado": batch_estado.finalizado,
        "generar_cuarto": batch_estado.generar_cuarto,
        "advertencias": batch_estado.advertencias,
        "total": total,
        "contadores": contadores,
        "casos": casos,
    }
