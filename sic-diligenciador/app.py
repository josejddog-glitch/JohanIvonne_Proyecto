"""Aplicación web local Flask para diligenciar resoluciones SIC.

Endpoints:
- GET  /              -> formulario de upload
- POST /upload        -> recibe archivos, crea caso, lanza pipeline async
- GET  /status/<id>   -> estado del caso (JSON)
- GET  /caso/<id>     -> página de seguimiento del caso
- GET  /download/<id>/<filename>  -> descarga archivo de salida
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for

import feedback_log
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB total upload

ROOT = Path(__file__).resolve().parent


def _lanzar_pipeline_async(caso_id: str, observaciones: str = "") -> None:
    def _run() -> None:
        try:
            pipeline.procesar_caso(caso_id, observaciones=observaciones)
        except Exception:
            logging.exception("Pipeline falló para caso %s", caso_id)

    t = threading.Thread(target=_run, name=f"pipeline-{caso_id}", daemon=True)
    t.start()


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/historial", methods=["GET"])
def historial():
    """Lista los últimos N casos procesados con metadatos básicos."""
    workspaces = ROOT / "workspaces"
    casos: list[dict] = []
    if workspaces.exists():
        for d in sorted(workspaces.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            estado_json = d / "estado.json"
            if not estado_json.exists():
                continue
            try:
                est = pipeline.cargar_estado(d.name)
                if est is None:
                    continue
            except Exception:
                continue
            sentido = ""
            resumen_path = d / "salida" / "resumen.md"
            if resumen_path.exists():
                try:
                    import re as _re
                    m = _re.search(
                        r"##\s*Sentido sugerido\s*\n.*?\*\*([A-ZÁÉÍÓÚ]+(?:\s+[A-ZÁÉÍÓÚ]+)?)\*\*",
                        resumen_path.read_text(encoding="utf-8"),
                        _re.DOTALL,
                    )
                    if m:
                        sentido = m.group(1)
                except Exception:
                    pass
            expediente = ""
            clas = est.clasificacion or {}
            if clas.get("expediente_principal"):
                expediente = Path(clas["expediente_principal"]).name
            casos.append({
                "caso_id": est.caso_id,
                "iniciado": est.iniciado,
                "estado": est.estado,
                "expediente": expediente,
                "sentido": sentido,
                "url_caso": url_for("caso", caso_id=est.caso_id),
                "descargas": [
                    {
                        "nombre": Path(p).name,
                        "url": url_for("download", caso_id=est.caso_id, filename=Path(p).name),
                    }
                    for p in (est.archivos_salida or [])
                ],
            })
            if len(casos) >= 50:
                break
    return jsonify({"casos": casos})


@app.route("/casos", methods=["GET"])
def pagina_historial():
    return render_template("historial.html")


@app.route("/upload", methods=["POST"])
def upload():
    archivos = request.files.getlist("archivos")
    if not archivos:
        return jsonify({"error": "No se subieron archivos"}), 400

    pares = [(f.filename or "archivo", f.read()) for f in archivos if f.filename]
    if not pares:
        return jsonify({"error": "Archivos vacíos"}), 400

    # Flag: si el checkbox "Generar CUARTA (Fallar)" está desmarcado, el modelo
    # solo extrae hechos (SEGUNDO + TERCERO) sin generar el análisis jurídico.
    generar_cuarto = request.form.get("generar_cuarto", "1") != "0"

    estado = pipeline.crear_caso(pares, generar_cuarto=generar_cuarto)
    _lanzar_pipeline_async(estado.caso_id)

    return jsonify({
        "caso_id": estado.caso_id,
        "url_estado": url_for("status", caso_id=estado.caso_id),
        "url_caso": url_for("caso", caso_id=estado.caso_id),
    })


@app.route("/status/<caso_id>", methods=["GET"])
def status(caso_id: str):
    estado = pipeline.cargar_estado(caso_id)
    if estado is None:
        return jsonify({"error": "Caso no existe"}), 404

    payload = estado.__dict__.copy()
    if estado.estado == "listo":
        payload["descargas"] = [
            {
                "nombre": Path(p).name,
                "url": url_for("download", caso_id=caso_id, filename=Path(p).name),
            }
            for p in estado.archivos_salida
        ]
    return jsonify(payload)


@app.route("/caso/<caso_id>", methods=["GET"])
def caso(caso_id: str):
    estado = pipeline.cargar_estado(caso_id)
    if estado is None:
        abort(404)
    return render_template("caso.html", caso_id=caso_id)


@app.route("/regenerar/<caso_id>", methods=["POST"])
def regenerar(caso_id: str):
    """Re-ejecuta el pipeline para un caso existente, inyectando las
    observaciones del abogado para guiar la nueva versión.

    Si `guardar_aprendizaje` es True, las observaciones se anexan también a
    `knowledge/learnings.md` para que se apliquen automáticamente a futuros casos.
    """
    estado = pipeline.cargar_estado(caso_id)
    if estado is None:
        return jsonify({"error": "Caso no existe"}), 404

    body = request.json or {}
    observaciones = (body.get("observaciones") or "").strip()
    guardar_aprendizaje = bool(body.get("guardar_aprendizaje", False))
    if not observaciones:
        return jsonify({"error": "Las observaciones no pueden estar vacías"}), 400

    if guardar_aprendizaje:
        learnings_path = ROOT / "knowledge" / "learnings.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        nueva_linea = f"\n- ({ts}, caso {caso_id}) {observaciones}\n"
        try:
            with learnings_path.open("a", encoding="utf-8") as f:
                f.write(nueva_linea)
            estado.agregar_log("Observaciones también guardadas como aprendizaje permanente.")
        except Exception as e:
            logging.exception("No se pudo escribir en learnings.md")
            estado.agregar_log(f"⚠️ No se pudo guardar aprendizaje: {e}")

    estado.estado = "pendiente"
    estado.error = ""
    estado.archivos_salida = []
    estado.agregar_log(f"Regeneración solicitada con observaciones ({len(observaciones)} chars).")
    pipeline._guardar_estado(estado)

    _lanzar_pipeline_async(caso_id, observaciones=observaciones)
    return jsonify({"caso_id": caso_id, "url_caso": url_for("caso", caso_id=caso_id)})


@app.route("/feedback/<caso_id>", methods=["POST"])
def feedback(caso_id: str):
    estado = pipeline.cargar_estado(caso_id)
    if estado is None:
        return jsonify({"error": "Caso no existe"}), 404

    data = request.json or {}
    sentido_correcto = (data.get("sentido_correcto") or "").strip().upper()
    sentido_sugerido = (data.get("sentido_sugerido") or "").strip().upper()
    calidad = data.get("calidad_general", 3)
    comentarios = (data.get("comentarios") or "").strip()
    secciones = data.get("secciones_problematicas") or []
    bloques_falt = (data.get("bloques_faltantes") or "").strip()

    registro = feedback_log.guardar_feedback(
        caso_id=caso_id,
        sentido_correcto=sentido_correcto,
        sentido_sugerido=sentido_sugerido,
        calidad_general=int(calidad),
        comentarios=comentarios,
        secciones_problematicas=secciones,
        bloques_faltantes=bloques_falt,
    )
    return jsonify({"ok": True, "registro": registro})


@app.route("/download/<caso_id>/<filename>", methods=["GET"])
def download(caso_id: str, filename: str):
    estado = pipeline.cargar_estado(caso_id)
    if estado is None:
        abort(404)
    salida_dir = Path(estado.workspace) / "salida"
    archivo = salida_dir / Path(filename).name
    if not archivo.exists():
        abort(404)
    return send_file(str(archivo), as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
