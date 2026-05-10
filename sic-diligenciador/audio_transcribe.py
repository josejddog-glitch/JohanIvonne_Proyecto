"""Transcribe audios a texto con timestamps usando faster-whisper (CPU-friendly).

Optimizaciones:
  - Modelo configurable vía SIC_WHISPER_MODEL (default: small).
  - Auto-pick de modelo según duración:
      * audios cortos (<= 20 min)  → modelo por defecto (small)
      * audios largos  (> 20 min)  → modelo `base` (mucho más rápido) + chunking paralelo
  - Chunking en bloques de 10 min con 5 s de overlap, transcripción paralela
    (4 workers) y deduplicación de segmentos en la zona de solape.
  - VAD activo, cuantización int8 en CPU.
  - Caché por hash MD5: re-procesos instantáneos.
  - `transcribir_varios()` paraleliza N audios distintos.

Salida: líneas `[HH:MM:SS] texto`.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPT_INICIAL_ES = (
    "Comcel, Tigo, Claro, Movistar, ETB, DirecTV, Avantel, WOM, "
    "Mbps, gigabytes, megas, decodificador, parrilla, comodato, "
    "promoción, tarifa, renta mensual, prepago, postpago, "
    "Resolución CRC, Superintendencia de Industria y Comercio, SIC."
)

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache" / "transcripciones"
DEFAULT_MODELO = os.environ.get("SIC_WHISPER_MODEL", "small")
MODELO_AUDIO_LARGO = os.environ.get("SIC_WHISPER_MODEL_LARGO", "base")

UMBRAL_AUDIO_LARGO_S = 20 * 60        # > 20 min → activar chunking + modelo base
CHUNK_SECONDS = 10 * 60               # bloques de 10 min
OVERLAP_SECONDS = 5                   # solape de 5s entre bloques (evita cortar palabras)
MAX_WORKERS_CHUNKS = 4
SAMPLE_RATE = 16000                   # faster-whisper espera 16kHz

# Cache de modelos cargados (loading es caro: ~5-10s por modelo).
_modelos: dict[str, object] = {}
_modelos_lock = threading.Lock()


def _formato_timestamp(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _hash_audio(audio_path: Path) -> str:
    h = hashlib.md5()
    with audio_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _obtener_modelo(nombre: str):
    """Carga (o reusa) un modelo Whisper. Thread-safe por nombre."""
    from faster_whisper import WhisperModel

    with _modelos_lock:
        if nombre not in _modelos:
            logger.info("Cargando WhisperModel(%s)...", nombre)
            _modelos[nombre] = WhisperModel(nombre, device="cpu", compute_type="int8")
        return _modelos[nombre]


def _decodificar_audio(audio_path: Path):
    """Carga el audio como numpy array float32 mono 16kHz."""
    from faster_whisper.audio import decode_audio
    return decode_audio(str(audio_path), sampling_rate=SAMPLE_RATE)


def _transcribir_array(audio_array, modelo: str, offset_segundos: float = 0.0) -> list[tuple[float, str]]:
    """Transcribe un numpy array y retorna [(start_abs, texto), ...]."""
    model = _obtener_modelo(modelo)
    segmentos, _info = model.transcribe(
        audio_array,
        language="es",
        initial_prompt=PROMPT_INICIAL_ES,
        vad_filter=True,
    )
    out: list[tuple[float, str]] = []
    for seg in segmentos:
        texto = seg.text.strip()
        if texto:
            out.append((seg.start + offset_segundos, texto))
    return out


def _chunkear(audio_array, chunk_s: int, overlap_s: int) -> list[tuple[float, "any"]]:
    """Parte un audio en chunks con overlap. Retorna [(start_abs, sub_array), ...]."""
    n = len(audio_array)
    duracion_s = n / SAMPLE_RATE
    if duracion_s <= chunk_s:
        return [(0.0, audio_array)]
    paso = chunk_s - overlap_s
    chunks: list[tuple[float, "any"]] = []
    cur = 0.0
    while cur < duracion_s:
        ini = int(cur * SAMPLE_RATE)
        fin = int(min(cur + chunk_s, duracion_s) * SAMPLE_RATE)
        chunks.append((cur, audio_array[ini:fin]))
        cur += paso
    return chunks


def _deduplicar(segmentos: list[tuple[float, str]], overlap_s: int) -> list[tuple[float, str]]:
    """Elimina segmentos duplicados en zonas de solape.

    Estrategia simple: ordenar por timestamp, descartar el segundo de cada par
    cuyo texto sea muy similar y cuyos timestamps difieran en menos de overlap_s.
    """
    if not segmentos:
        return segmentos
    segmentos = sorted(segmentos, key=lambda x: x[0])
    out: list[tuple[float, str]] = []
    for ts, texto in segmentos:
        if out and (ts - out[-1][0]) < overlap_s:
            ant = out[-1][1].lower().strip()
            cur = texto.lower().strip()
            if ant == cur or ant.startswith(cur[:30]) or cur.startswith(ant[:30]):
                continue  # duplicado en zona de solape
        out.append((ts, texto))
    return out


def _formatear_segmentos(segmentos: list[tuple[float, str]]) -> str:
    return "\n".join(f"[{_formato_timestamp(ts)}] {texto}" for ts, texto in segmentos)


def transcribir(audio_path: Path, modelo: str | None = None) -> str:
    """Transcribe un audio a texto con timestamps.

    Si el audio es > 20 min: usa modelo `base` + chunking paralelo automáticamente.
    Si es más corto: usa el modelo por defecto (small) sin chunking.
    `modelo` override fuerza ese modelo independiente de la duración.
    """
    audio = _decodificar_audio(audio_path)
    duracion_s = len(audio) / SAMPLE_RATE
    es_largo = duracion_s > UMBRAL_AUDIO_LARGO_S
    modelo_efectivo = modelo or (MODELO_AUDIO_LARGO if es_largo else DEFAULT_MODELO)

    if not es_largo:
        logger.info(
            "Audio %s: %.1f min con modelo %s (sin chunking).",
            audio_path.name, duracion_s / 60, modelo_efectivo,
        )
        segmentos = _transcribir_array(audio, modelo_efectivo)
        return _formatear_segmentos(segmentos)

    # Audio largo: chunks paralelos
    chunks = _chunkear(audio, CHUNK_SECONDS, OVERLAP_SECONDS)
    logger.info(
        "Audio %s: %.1f min con modelo %s en %d chunks paralelos (max %d workers).",
        audio_path.name, duracion_s / 60, modelo_efectivo, len(chunks), MAX_WORKERS_CHUNKS,
    )

    todos: list[tuple[float, str]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_CHUNKS, len(chunks))) as ex:
        futuros = {
            ex.submit(_transcribir_array, sub_audio, modelo_efectivo, offset): offset
            for offset, sub_audio in chunks
        }
        for fut in as_completed(futuros):
            try:
                todos.extend(fut.result())
            except Exception as e:
                logger.exception("Chunk de %ss falló: %s", futuros[fut], e)

    return _formatear_segmentos(_deduplicar(todos, OVERLAP_SECONDS))


def transcribir_a_archivo(
    audio_path: Path,
    salida_dir: Path,
    modelo: str | None = None,
    usar_cache: bool = True,
) -> Path:
    """Transcribe y guarda el resultado en `salida_dir/<stem>.txt`. Caché por hash MD5."""
    salida_dir.mkdir(parents=True, exist_ok=True)
    salida_path = salida_dir / f"{audio_path.stem}.txt"

    cache_path = None
    if usar_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            h = _hash_audio(audio_path)
            cache_path = CACHE_DIR / f"{h}.txt"
            if cache_path.exists():
                salida_path.write_text(cache_path.read_text(encoding="utf-8"), encoding="utf-8")
                return salida_path
        except Exception:
            cache_path = None

    contenido = transcribir(audio_path, modelo=modelo)
    salida_path.write_text(contenido, encoding="utf-8")
    if cache_path is not None:
        try:
            cache_path.write_text(contenido, encoding="utf-8")
        except Exception:
            pass
    return salida_path


def transcribir_varios(
    audios: list[Path],
    salida_dir: Path,
    modelo: str | None = None,
    max_workers: int = 2,
    usar_cache: bool = True,
) -> list[Path]:
    """Transcribe varios audios en paralelo (entre archivos)."""
    if not audios:
        return []
    if len(audios) == 1 or max_workers <= 1:
        return [transcribir_a_archivo(a, salida_dir, modelo=modelo, usar_cache=usar_cache) for a in audios]

    resultados: dict[Path, Path] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futuros = {
            ex.submit(transcribir_a_archivo, a, salida_dir, modelo, usar_cache): a
            for a in audios
        }
        for fut in as_completed(futuros):
            a = futuros[fut]
            resultados[a] = fut.result()
    return [resultados[a] for a in audios]
