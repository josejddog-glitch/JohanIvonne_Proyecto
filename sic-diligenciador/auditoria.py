"""Log de auditoría persistente por caso.

Cada caso terminado (con éxito o error) deja una fila en `audit.csv` para
poder analizar patrones: tiempo total, sentido sugerido, bloques usados,
errores, etc.
"""
from __future__ import annotations

import csv
import json
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIT_CSV = ROOT / "audit.csv"

# Lock global: protege audit.csv contra escrituras concurrentes desde múltiples
# workers (futuro paralelismo). Hoy el worker de batch.py es único, así que
# el lock no contiende, pero deja la fundación lista.
_audit_lock = threading.Lock()

CAMPOS = [
    "caso_id",
    "fecha",
    "estado",
    "duracion_seg",
    "n_archivos_entrada",
    "n_audios",
    "expediente_principal",
    "tipologias_detectadas",
    "bloques_usados",
    "sentido_sugerido",
    "n_verificar",
    "tiempo_revision_humana",
    "error",
]


def _parse_resumen_md(contenido: str) -> dict:
    """Extrae datos estructurados del resumen.md generado por Claude."""
    out = {
        "tipologias": "",
        "bloques": "",
        "sentido": "",
        "n_verificar": 0,
        "tiempo_revision": "",
    }

    def _seccion(titulo: str) -> str:
        m = re.search(
            rf"##\s*{re.escape(titulo)}\s*\n(.*?)(?=\n##|\Z)",
            contenido,
            re.DOTALL | re.IGNORECASE,
        )
        return (m.group(1).strip() if m else "")

    out["tipologias"] = _seccion("Tipologías detectadas").replace("\n", " | ")[:500]
    out["bloques"] = _seccion("Bloques jurídicos usados").replace("\n", " | ")[:500]

    sentido_sec = _seccion("Sentido sugerido")
    m_sentido = re.search(r"\*\*(\w+(?:\s+\w+)?)\*\*", sentido_sec)
    if m_sentido:
        out["sentido"] = m_sentido.group(1)

    out["n_verificar"] = len(re.findall(r"\[VERIFICAR:", contenido))

    tiempo_sec = _seccion("Tiempo estimado de revisión humana")
    m_tiempo = re.search(r"\*\*(\w+)\*\*", tiempo_sec)
    if m_tiempo:
        out["tiempo_revision"] = m_tiempo.group(1)

    return out


def registrar(estado: object) -> None:
    """Append una fila en audit.csv basado en el estado final del caso.

    Args:
        estado: instancia de pipeline.CasoEstado.
    """
    workspace = Path(getattr(estado, "workspace"))
    resumen_path = workspace / "salida" / "resumen.md"

    parsed = {"tipologias": "", "bloques": "", "sentido": "", "n_verificar": 0, "tiempo_revision": ""}
    if resumen_path.exists():
        try:
            parsed = _parse_resumen_md(resumen_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    iniciado = getattr(estado, "iniciado", "")
    finalizado = getattr(estado, "finalizado", "")
    duracion = ""
    try:
        if iniciado and finalizado:
            t0 = datetime.fromisoformat(iniciado)
            t1 = datetime.fromisoformat(finalizado)
            duracion = f"{(t1 - t0).total_seconds():.0f}"
    except Exception:
        pass

    clas = getattr(estado, "clasificacion", None) or {}
    n_audios = len(clas.get("audios", []) or [])
    n_total = (
        n_audios
        + len(clas.get("anexos_pdf", []) or [])
        + len(clas.get("anexos_doc", []) or [])
        + (1 if clas.get("expediente_principal") else 0)
    )
    expediente = clas.get("expediente_principal") or ""
    if expediente:
        expediente = Path(expediente).name

    fila = {
        "caso_id": getattr(estado, "caso_id", ""),
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "estado": getattr(estado, "estado", ""),
        "duracion_seg": duracion,
        "n_archivos_entrada": n_total,
        "n_audios": n_audios,
        "expediente_principal": expediente,
        "tipologias_detectadas": parsed["tipologias"],
        "bloques_usados": parsed["bloques"],
        "sentido_sugerido": parsed["sentido"],
        "n_verificar": parsed["n_verificar"],
        "tiempo_revision_humana": parsed["tiempo_revision"],
        "error": (getattr(estado, "error", "") or "")[:500],
    }

    with _audit_lock:
        nuevo = not AUDIT_CSV.exists()
        with AUDIT_CSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            if nuevo:
                w.writeheader()
            w.writerow(fila)
