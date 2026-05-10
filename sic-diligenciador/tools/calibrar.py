"""Resume el feedback acumulado y sugiere ajustes a la base de conocimiento.

Uso:
    python tools/calibrar.py

Lee `feedback.jsonl` y `audit.csv` y produce `tools/reporte_calibracion.md`
con métricas y observaciones para que el usuario decida qué bloques o reglas
ajustar.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import feedback_log  # noqa: E402

AUDIT_CSV = ROOT / "audit.csv"
REPORTE = ROOT / "tools" / "reporte_calibracion.md"


def leer_audit() -> list[dict]:
    if not AUDIT_CSV.exists():
        return []
    with AUDIT_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    feedback = feedback_log.leer_todos()
    audit = leer_audit()

    if not feedback and not audit:
        print("Sin datos: aún no hay casos procesados ni feedback registrado.")
        return 1

    lineas = [
        f"# Reporte de calibración – {datetime.now().isoformat(timespec='minutes')}",
        "",
        f"- Casos procesados (`audit.csv`): **{len(audit)}**",
        f"- Casos con feedback humano (`feedback.jsonl`): **{len(feedback)}**",
        "",
    ]

    if audit:
        sentidos = Counter(r["sentido_sugerido"] for r in audit if r["sentido_sugerido"])
        tipologias = Counter()
        bloques = Counter()
        for r in audit:
            for t in (r["tipologias_detectadas"] or "").split("|"):
                t = t.strip(" -*")
                if t:
                    tipologias[t[:80]] += 1
            for b in (r["bloques_usados"] or "").split("|"):
                b = b.strip(" -*")
                if b:
                    bloques[b[:80]] += 1
        duraciones = [int(r["duracion_seg"]) for r in audit if r["duracion_seg"].isdigit()]
        prom = sum(duraciones) / len(duraciones) if duraciones else 0
        n_verificar = [int(r["n_verificar"]) for r in audit if r["n_verificar"].isdigit()]
        prom_v = sum(n_verificar) / len(n_verificar) if n_verificar else 0

        lineas += [
            "## Métricas operativas",
            f"- Duración promedio por caso: **{prom:.0f} seg** (~{prom/60:.1f} min)",
            f"- Promedio de marcadores `[VERIFICAR:]` por caso: **{prom_v:.1f}**",
            "",
            "## Distribución de sentidos sugeridos",
            *[f"- {s}: {n}" for s, n in sentidos.most_common()],
            "",
            "## Tipologías más frecuentes",
            *[f"- {t}: {n}" for t, n in tipologias.most_common(15)],
            "",
            "## Bloques más usados",
            *[f"- {b}: {n}" for b, n in bloques.most_common(15)],
            "",
        ]

    if feedback:
        aciertos = sum(1 for f in feedback if f.get("sentido_acertado"))
        total = sum(1 for f in feedback if f.get("sentido_acertado") is not None)
        calidades = [f["calidad_general"] for f in feedback if f.get("calidad_general")]
        prom_cal = sum(calidades) / len(calidades) if calidades else 0
        secciones = Counter()
        for f in feedback:
            for s in f.get("secciones_problematicas", []):
                secciones[s] += 1
        bloques_falt = Counter(f["bloques_faltantes"] for f in feedback if f.get("bloques_faltantes"))

        lineas += [
            "## Calidad reportada por humano",
            f"- Sentido acertado: **{aciertos}/{total}** ({(aciertos/total*100 if total else 0):.0f}%)",
            f"- Calidad general promedio: **{prom_cal:.2f} / 5**",
            "",
            "## Secciones problemáticas más reportadas",
            *[f"- {s}: {n}" for s, n in secciones.most_common()],
            "",
            "## Bloques que el usuario marcó como faltantes",
            *[f"- {b}: {n}" for b, n in bloques_falt.most_common()],
            "",
            "## Comentarios libres recientes (últimos 10)",
            *[f"- ({f['fecha'][:10]}) caso {f['caso_id']}: {f.get('comentarios','').strip()[:300]}"
              for f in feedback[-10:]],
            "",
        ]

    lineas += [
        "## Sugerencias automáticas",
        "_Estas son heurísticas — el usuario debe validar antes de aplicar._",
        "",
    ]

    if feedback:
        if total and aciertos / total < 0.8:
            lineas.append(
                "- ⚠️ Tasa de acierto del sentido por debajo del 80%. Revisar `prompts/caso.md.j2` "
                "y `knowledge/tipologias.md` para reforzar las reglas de selección."
            )
        for s, n in secciones.most_common(3):
            lineas.append(
                f"- 🔧 Sección frecuentemente problemática: **{s}** (reportada {n} veces). "
                f"Revisar la frase ancla y el bloque correspondiente."
            )
        for b, n in bloques_falt.most_common(3):
            if b:
                lineas.append(
                    f"- 📚 Bloque faltante reportado: **{b}** (mencionado {n} veces). "
                    f"Considerar crear `knowledge/bloques/<nombre>.md` y agregar fila en `tipologias.md`."
                )

    REPORTE.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Reporte generado: {REPORTE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
