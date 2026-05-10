"""Captura el feedback estructurado del usuario sobre cada caso.

Se almacena como JSONL (un caso por línea) para poder consumirse desde la
herramienta de calibración (`tools/calibrar.py`).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEEDBACK_JSONL = ROOT / "feedback.jsonl"


def guardar_feedback(
    caso_id: str,
    sentido_correcto: str,
    sentido_sugerido: str,
    calidad_general: int,
    comentarios: str,
    secciones_problematicas: list[str] | None = None,
    bloques_faltantes: str = "",
) -> dict:
    """Persiste un registro de feedback. Retorna el dict guardado."""
    registro = {
        "caso_id": caso_id,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "sentido_correcto": sentido_correcto,  # CONFIRMA / MODIFICA / REVOCA / IMPROCEDENTE / OTRO
        "sentido_sugerido_por_ia": sentido_sugerido,
        "sentido_acertado": (
            sentido_correcto.upper() == sentido_sugerido.upper() if sentido_sugerido else None
        ),
        "calidad_general": int(calidad_general),  # 1-5
        "comentarios": comentarios,
        "secciones_problematicas": secciones_problematicas or [],
        "bloques_faltantes": bloques_faltantes,
    }
    with FEEDBACK_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def leer_todos() -> list[dict]:
    """Carga todos los registros de feedback."""
    if not FEEDBACK_JSONL.exists():
        return []
    out = []
    with FEEDBACK_JSONL.open("r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                try:
                    out.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    return out
