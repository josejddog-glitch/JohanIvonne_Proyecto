"""Corre los 4 ejemplos como casos del pipeline y compara contra la solución real.

Uso:
    python tests/golden/run_golden.py [--solo ejemplo_original]

Para cada ejemplo:
  1. Crea un workspace nuevo a partir de los archivos de `Expediente y anexos/`.
  2. Corre el pipeline.
  3. Compara `resolucion_diligenciada.docx` vs el .docx solución del ejemplo.
  4. Imprime un reporte (sentido acertado, secciones presentes, similitud Jaccard).

NOTA: Esto invoca Claude Code CLI repetidamente y consume cuota Pro. No correr
todos a la vez sin necesidad — usar `--solo <nombre>` para iterar solo uno.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pipeline  # noqa: E402

EJEMPLOS_DIR = ROOT / "knowledge" / "ejemplos"


def extraer_texto_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extraer_sentido(texto: str) -> str:
    """Heurística: busca CONFIRMA/MODIFICA/REVOCA/IMPROCEDENTE en orden de aparición."""
    palabras = ["CONFIRMA", "MODIFICA", "REVOCA", "IMPROCEDENTE"]
    matches = [(p, m.start()) for p in palabras for m in re.finditer(rf"\b{p}\b", texto)]
    matches.sort(key=lambda x: x[1])
    return matches[0][0] if matches else "NO_DETECTADO"


def jaccard(a: str, b: str) -> float:
    """Similitud Jaccard sobre tokens en minúscula (palabras de >=4 chars)."""
    tok = lambda s: set(re.findall(r"[a-záéíóúñ]{4,}", s.lower()))
    A, B = tok(a), tok(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def encontrar_carpeta_anexos(ejemplo_dir: Path) -> Path:
    for nombre in ["Expediente y anexos", "Expedientes y anexos"]:
        p = ejemplo_dir / nombre
        if p.exists():
            return p
    raise FileNotFoundError(f"No se encontró carpeta de anexos en {ejemplo_dir}")


def encontrar_solucion(ejemplo_dir: Path) -> Path | None:
    for d in ejemplo_dir.iterdir():
        if d.is_file() and d.suffix.lower() == ".docx":
            return d
    return None


def correr_ejemplo(ejemplo_dir: Path) -> dict:
    nombre = ejemplo_dir.name
    print(f"\n=== {nombre} ===")
    anexos_dir = encontrar_carpeta_anexos(ejemplo_dir)
    solucion = encontrar_solucion(ejemplo_dir)
    if solucion is None:
        return {"ejemplo": nombre, "error": "sin solucion .docx"}

    pares = [(f.name, f.read_bytes()) for f in anexos_dir.iterdir() if f.is_file()]
    print(f"  Archivos: {len(pares)}")
    estado = pipeline.crear_caso(pares)
    t0 = time.time()
    try:
        estado_final = pipeline.procesar_caso(estado.caso_id)
    except Exception as e:
        return {"ejemplo": nombre, "error": str(e)[:300]}
    dur = time.time() - t0

    salida_docx = Path(estado_final.workspace) / "salida" / "resolucion_diligenciada.docx"
    salida_resumen = Path(estado_final.workspace) / "salida" / "resumen.md"
    if not salida_docx.exists():
        return {"ejemplo": nombre, "error": "no se generó .docx"}

    texto_salida = extraer_texto_docx(salida_docx)
    texto_solucion = extraer_texto_docx(solucion)
    sentido_salida = extraer_sentido(texto_salida)
    sentido_solucion = extraer_sentido(texto_solucion)
    sim = jaccard(texto_salida, texto_solucion)
    n_verificar = len(re.findall(r"\[VERIFICAR:", texto_salida))

    return {
        "ejemplo": nombre,
        "duracion_seg": round(dur, 1),
        "sentido_real": sentido_solucion,
        "sentido_propuesto": sentido_salida,
        "sentido_acertado": sentido_salida == sentido_solucion,
        "similitud_jaccard": round(sim, 3),
        "n_verificar": n_verificar,
        "salida_docx": str(salida_docx),
        "salida_resumen": str(salida_resumen),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solo", help="nombre exacto de un ejemplo (ej: ejemplo_original)")
    args = parser.parse_args()

    ejemplos = sorted(d for d in EJEMPLOS_DIR.iterdir() if d.is_dir())
    if args.solo:
        ejemplos = [d for d in ejemplos if d.name == args.solo]
        if not ejemplos:
            print(f"No se encontró ejemplo: {args.solo}")
            sys.exit(1)

    resultados = []
    for ej in ejemplos:
        resultados.append(correr_ejemplo(ej))

    print("\n\n========== REPORTE GOLDEN ==========")
    for r in resultados:
        print(r)
    aciertos = sum(1 for r in resultados if r.get("sentido_acertado"))
    total = sum(1 for r in resultados if "sentido_acertado" in r)
    print(f"\nSentido acertado: {aciertos}/{total}")
    if total:
        prom_sim = sum(r.get("similitud_jaccard", 0) for r in resultados) / len(resultados)
        print(f"Similitud Jaccard promedio: {prom_sim:.3f}")


if __name__ == "__main__":
    main()
