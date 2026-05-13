"""OCR de PDFs (nativos, escaneados e híbridos) con Tesseract + Poppler.

Convierte un PDF en un .txt estructurado por página, que es 5-8x más rápido y
barato para Claude que leer cada página como imagen.

Estrategia híbrida (v2):
  1. Extracción inicial con pypdf por página.
  2. Si el PDF es totalmente escaneado (promedio < umbral): Tesseract en todas
     las páginas.
  3. Si el PDF es híbrido (texto en algunas páginas, imagen en otras):
     - Detecta páginas "huérfanas" cuyo contenido único (excluyendo header
       boilerplate recurrente) es menor al umbral.
     - Corre Tesseract solo en esas páginas y mezcla los resultados.
  4. Caché por hash MD5 + versión del código: re-procesar el mismo PDF es
     instantáneo, pero un cambio de versión invalida caches anteriores.

Configuración (rutas de Tesseract y Poppler):
  - `TESSERACT_EXE`: por defecto `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`.
  - `POPPLER_BIN`: por defecto el directorio de winget (oschwartz10612.Poppler).
  - `TESSDATA_LOCAL`: directorio local con los .traineddata (incluye `spa`).

Variables de entorno: `SIC_TESSERACT_EXE`, `SIC_POPPLER_BIN`, `SIC_TESSDATA_DIR`.
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

# Defaults para Windows con winget
_DEFAULT_TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_DEFAULT_TESSDATA = str(ROOT / "bin" / "tessdata")


def _autodetect_poppler() -> str:
    """Busca Poppler en ubicaciones típicas de winget/conda/chocolatey/manual.

    Retorna la ruta del directorio `bin` que contiene `pdftoppm.exe`, o
    string vacío si no se encuentra. Funciona en cualquier PC sin necesidad
    de configurar variables de entorno.
    """
    candidatos: list[Path] = []

    # 1. winget (path dinámico según usuario)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            # Buscar cualquier subcarpeta que empiece con "oschwartz10612.Poppler"
            for poppler_pkg in winget_dir.glob("oschwartz10612.Poppler*"):
                # Estructura típica: <pkg>/poppler-X.Y.Z/Library/bin
                for bin_dir in poppler_pkg.glob("poppler-*/Library/bin"):
                    candidatos.append(bin_dir)

    # 2. Chocolatey
    candidatos.append(Path(r"C:\ProgramData\chocolatey\lib\poppler\tools\Library\bin"))

    # 3. Instalación manual común
    candidatos.append(Path(r"C:\poppler\Library\bin"))
    candidatos.append(Path(r"C:\Program Files\poppler\Library\bin"))

    # 4. Conda
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidatos.append(Path(conda_prefix) / "Library" / "bin")

    for c in candidatos:
        if c.exists() and (c / "pdftoppm.exe").exists():
            return str(c)
    return ""


TESSERACT_EXE = os.environ.get("SIC_TESSERACT_EXE", _DEFAULT_TESS)
POPPLER_BIN = os.environ.get("SIC_POPPLER_BIN") or _autodetect_poppler()
TESSDATA_LOCAL = os.environ.get("SIC_TESSDATA_DIR", _DEFAULT_TESSDATA)

CACHE_DIR = ROOT / "cache" / "ocr"
CACHE_VERSION = "v3-hibrido"  # cambiar al modificar el algoritmo invalida caches viejos
MIN_TEXT_PER_PAGE = 30  # umbral para considerar el PDF entero como escaneado
# Una pagina cuyo contenido unico (sin boilerplate) sea menor a este umbral se
# considera huerfana y se OCR-iza con Tesseract. 250 cubre paginas que solo
# contienen un rotulo de indice tipo "Folio 4. RESPUESTA DE COMCEL S.A. AL
# DERECHO DE PETICION PQR ... CUN ..." (~110 chars) que indican que el contenido
# real es escaneado.
MIN_UNIQUE_CONTENT_PER_PAGE = 250
BOILERPLATE_THRESHOLD = 0.7  # líneas que aparecen en >=70% de páginas son boilerplate


def _hash_pdf(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extraer_textos_pypdf(pdf_path: Path) -> tuple[list[str], bool]:
    """Extrae texto con pypdf por página. Retorna (textos_por_pagina, es_escaneado_total)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        textos: list[str] = []
        chars_total = 0
        for page in reader.pages:
            t = page.extract_text() or ""
            chars_total += len(t.strip())
            textos.append(t)
        es_escaneado_total = (chars_total / max(len(reader.pages), 1)) < MIN_TEXT_PER_PAGE
        return textos, es_escaneado_total
    except Exception as e:
        logger.warning("pypdf falló: %s", e)
        return [], True


def _detectar_paginas_huerfanas(
    textos: list[str], umbral_unico: int = MIN_UNIQUE_CONTENT_PER_PAGE
) -> list[int]:
    """Detecta páginas cuyo contenido único es menor al umbral.

    Las páginas con header/footer recurrente (que aparecen en >=70% de las
    páginas) se descuentan. Una página con solo el header + un rótulo del
    índice se considera huérfana porque el contenido real es escaneado.

    Retorna índices 0-indexed de las páginas a OCR con Tesseract.
    """
    if len(textos) <= 1:
        return [i for i, t in enumerate(textos) if len(t.strip()) < umbral_unico]

    # Contar líneas recurrentes
    line_counter: Counter = Counter()
    for t in textos:
        lineas_unicas_pagina = {l.strip() for l in t.splitlines() if l.strip()}
        for l in lineas_unicas_pagina:
            line_counter[l] += 1
    n = len(textos)
    boilerplate = {l for l, c in line_counter.items() if c >= n * BOILERPLATE_THRESHOLD}

    huerfanas: list[int] = []
    for i, t in enumerate(textos):
        unique_lines = [
            l.strip() for l in t.splitlines() if l.strip() and l.strip() not in boilerplate
        ]
        unique_text = " ".join(unique_lines).strip()
        if len(unique_text) < umbral_unico:
            huerfanas.append(i)
    return huerfanas


def _ocr_pagina_individual(pdf_path: Path, indice_0: int, dpi: int = 300) -> str:
    """Rasteriza y aplica Tesseract a una sola página (0-indexed) del PDF."""
    import pytesseract
    from pdf2image import convert_from_path

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    os.environ["TESSDATA_PREFIX"] = TESSDATA_LOCAL

    pages = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        poppler_path=POPPLER_BIN,
        fmt="png",
        first_page=indice_0 + 1,
        last_page=indice_0 + 1,
    )
    if not pages:
        return ""
    return pytesseract.image_to_string(pages[0], lang="spa", config="--psm 6").strip()


def _ocr_todas_paginas_tesseract(pdf_path: Path, dpi: int = 300) -> list[str]:
    """Rasteriza todo el PDF y aplica Tesseract a cada página."""
    import pytesseract
    from pdf2image import convert_from_path

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    os.environ["TESSDATA_PREFIX"] = TESSDATA_LOCAL

    paginas = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        poppler_path=POPPLER_BIN,
        fmt="png",
        thread_count=2,
    )
    config = "--psm 6"
    return [pytesseract.image_to_string(img, lang="spa", config=config).strip() for img in paginas]


def ocr_pdf_a_txt(pdf_path: Path, salida_dir: Path, usar_cache: bool = True) -> Path:
    """Procesa un PDF y guarda el texto resultante en `salida_dir/<stem>_ocr.txt`.

    Estrategia híbrida:
      - Si pypdf rinde texto promedio bajo: Tesseract en todas las páginas.
      - Si pypdf rinde bien pero hay páginas huérfanas (escaneos intercalados):
        Tesseract solo en esas páginas, pypdf en el resto.
      - Si todo bien con pypdf: solo pypdf.

    El resultado se cachea por hash + versión del código.
    """
    salida_dir.mkdir(parents=True, exist_ok=True)
    out_path = salida_dir / f"{pdf_path.stem}_ocr.txt"

    cache_path = None
    if usar_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            h = _hash_pdf(pdf_path)
            cache_path = CACHE_DIR / f"{h}_{CACHE_VERSION}.txt"
            if cache_path.exists():
                out_path.write_text(cache_path.read_text(encoding="utf-8"), encoding="utf-8")
                return out_path
        except Exception:
            cache_path = None

    textos_pypdf, es_escaneado_total = _extraer_textos_pypdf(pdf_path)
    paginas_ocr_tesseract: list[int] = []

    if es_escaneado_total:
        logger.info("PDF totalmente escaneado, corriendo Tesseract en todo el documento...")
        textos_finales = _ocr_todas_paginas_tesseract(pdf_path)
        paginas_ocr_tesseract = list(range(len(textos_finales)))
        encabezado = (
            f"# OCR Tesseract+Poppler (idioma: spa, todas las páginas)\n"
            f"# Fuente: {pdf_path.name}\n\n"
        )
    else:
        # PDF nativo o híbrido: detectar páginas huérfanas para OCR puntual
        textos_finales = list(textos_pypdf)
        huerfanas = _detectar_paginas_huerfanas(textos_pypdf)
        if huerfanas and Path(TESSERACT_EXE).exists():
            logger.info(
                "PDF híbrido: %d página(s) huérfana(s) detectada(s) en %d total. "
                "Corriendo Tesseract en %s.",
                len(huerfanas),
                len(textos_pypdf),
                [i + 1 for i in huerfanas],
            )
            for idx in huerfanas:
                try:
                    txt_tesseract = _ocr_pagina_individual(pdf_path, idx)
                    if txt_tesseract:
                        # Reemplazar el contenido pypdf (mayormente vacío) por el de Tesseract
                        textos_finales[idx] = txt_tesseract
                        paginas_ocr_tesseract.append(idx)
                except Exception as e:
                    logger.warning("Tesseract falló en página %d: %s", idx + 1, e)
        if paginas_ocr_tesseract:
            encabezado = (
                f"# Texto híbrido pypdf + Tesseract\n"
                f"# Fuente: {pdf_path.name}\n"
                f"# Páginas con OCR Tesseract (eran escaneos): "
                f"{[i + 1 for i in paginas_ocr_tesseract]}\n\n"
            )
        else:
            encabezado = (
                f"# Texto extraído con pypdf (PDF nativo, sin páginas huérfanas)\n"
                f"# Fuente: {pdf_path.name}\n\n"
            )

    bloques = [
        f"=== PÁGINA {i + 1} ==={(' (OCR Tesseract)' if i in paginas_ocr_tesseract else '')}\n{t.strip()}"
        for i, t in enumerate(textos_finales)
    ]
    contenido = encabezado + "\n\n".join(bloques)
    out_path.write_text(contenido, encoding="utf-8")
    if cache_path is not None:
        try:
            cache_path.write_text(contenido, encoding="utf-8")
        except Exception:
            pass
    return out_path


def disponible() -> bool:
    """Heurística: chequea si Tesseract y Poppler existen donde esperamos."""
    return bool(POPPLER_BIN) and Path(TESSERACT_EXE).exists() and Path(POPPLER_BIN).exists()


def diagnosticar() -> dict:
    """Diagnóstico completo del entorno OCR. Útil para troubleshooting al
    instalar el programa en un PC nuevo. Retorna dict con cada componente
    y si está disponible.
    """
    return {
        "tesseract_exe": TESSERACT_EXE,
        "tesseract_ok": Path(TESSERACT_EXE).exists(),
        "poppler_bin": POPPLER_BIN or "(no detectado)",
        "poppler_ok": bool(POPPLER_BIN) and Path(POPPLER_BIN).exists(),
        "tessdata_dir": TESSDATA_LOCAL,
        "tessdata_ok": Path(TESSDATA_LOCAL).exists() and (Path(TESSDATA_LOCAL) / "spa.traineddata").exists(),
    }
