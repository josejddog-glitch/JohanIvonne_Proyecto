"""Construye `resumen.md` a partir del JSON estructurado de Claude."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def construir(salida_path: Path, caso_id: str, datos: dict[str, Any]) -> Path:
    """Escribe el resumen.md y retorna la ruta."""
    salida_path.parent.mkdir(parents=True, exist_ok=True)

    resumen = datos.get("resumen", {}) or {}
    tipologias = datos.get("tipologias", []) or []
    bloques_usados = datos.get("bloques_usados", []) or []

    lineas: list[str] = [
        f"# Resumen del caso {caso_id}",
        "",
        "## Tipologías detectadas",
    ]
    if tipologias:
        for t in tipologias:
            if isinstance(t, dict):
                lineas.append(f"- {t.get('nombre', '?')}")
            else:
                lineas.append(f"- {t}")
    else:
        lineas.append("- (no detectadas)")

    lineas += ["", "## Bloques jurídicos usados"]
    if bloques_usados:
        for b in bloques_usados:
            lineas.append(f"- bloques/{b}")
    else:
        lineas.append("- (ninguno)")

    sentido = resumen.get("sentido_sugerido", "?")
    lineas += ["", "## Sentido sugerido", f"**{sentido}**", ""]

    lineas.append("## Argumentos a favor del sentido propuesto")
    args = resumen.get("argumentos_a_favor", []) or []
    if args:
        for i, a in enumerate(args, 1):
            lineas.append(f"{i}. {a}")
    else:
        lineas.append("(no se registraron)")

    lineas += ["", "## Puntos débiles / contraargumentos posibles"]
    debs = resumen.get("puntos_debiles", []) or []
    if debs:
        for i, a in enumerate(debs, 1):
            lineas.append(f"{i}. {a}")
    else:
        lineas.append("(no se registraron)")

    lineas += ["", "## Evidencia citada en la resolución",
               "| # | Cita | Fuente |", "|---|---|---|"]
    evid = resumen.get("evidencia_citada", []) or []
    if evid:
        for i, ev in enumerate(evid, 1):
            cita = (ev.get("cita") or "").replace("|", "\\|")
            fuente = (ev.get("fuente") or "").replace("|", "\\|")
            lineas.append(f"| {i} | {cita} | {fuente} |")
    else:
        lineas.append("| — | — | — |")

    lineas += ["", "## Datos a verificar manualmente"]
    verif = resumen.get("datos_a_verificar", []) or []
    if verif:
        for v in verif:
            lineas.append(f"- {v}")
    else:
        lineas.append("- (ninguno)")

    tiempo = resumen.get("tiempo_revision_humana", "medio")
    lineas += ["", "## Tiempo estimado de revisión humana", f"**{tiempo}**"]

    contenido = "\n".join(lineas) + "\n"
    salida_path.write_text(contenido, encoding="utf-8")
    return salida_path
