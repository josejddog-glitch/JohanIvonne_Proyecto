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

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

import batch
import feedback_log
import pipeline

# Logging a consola Y a archivo persistente (útil cuando se arranca via
# iniciar.vbs que oculta la ventana). El archivo rota implícitamente cada
# vez que se reinicia el servidor.
_LOG_PATH = Path(__file__).resolve().parent / "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_LOG_PATH), mode="a", encoding="utf-8"),
    ],
)

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
def raiz():
    """La vista por defecto es el modo lote. Para el modo de un solo caso
    usar `/individual`.
    """
    return redirect(url_for("pagina_batch_upload"))


@app.route("/individual", methods=["GET"])
def index():
    """Modo upload de UN solo caso (mantenido por compatibilidad)."""
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

    # Flag: si el checkbox "Generar CUARTA (Fallar)" está marcado, el modelo
    # genera el análisis jurídico. Por defecto OFF (solo extrae hechos).
    generar_cuarto = request.form.get("generar_cuarto", "0") == "1"

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
    # Agregar duración en segundos (None si todavía no empezó)
    if estado.estado in {"en_cola", "pendiente"}:
        payload["duracion_seg"] = None
    else:
        payload["duracion_seg"] = batch._duracion_seg(estado.iniciado, estado.finalizado)
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


# ============================================================
# Batch (lote): procesar varios casos en un solo ZIP, secuencial.
# ============================================================

@app.route("/batch", methods=["GET"])
def pagina_batch_upload():
    """Página de upload de ZIP (modo lote)."""
    return render_template("batch.html", batch_id=None)


@app.route("/batch/upload", methods=["POST"])
def batch_upload():
    """Recibe un ZIP y crea N casos como PREVIEW (estado pendiente, sin encolar).
    El usuario después debe confirmar via /batch/<id>/iniciar para empezar
    el procesamiento real.
    """
    zip_file = request.files.get("zip")
    if zip_file is None or not zip_file.filename:
        return jsonify({"error": "No se subió ningún archivo ZIP."}), 400
    if not zip_file.filename.lower().endswith(".zip"):
        return jsonify({"error": "El archivo debe ser .zip."}), 400

    generar_cuarto = request.form.get("generar_cuarto", "0") == "1"
    try:
        estado = batch.crear_batch_preview(zip_file.read(), generar_cuarto=generar_cuarto)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.exception("Error procesando ZIP")
        return jsonify({"error": f"Error inesperado: {e}"}), 500

    # Devolvemos info detallada para que el frontend muestre el modal de
    # confirmación con los nombres de los casos detectados.
    nombres_lista = [estado.nombres[cid] for cid in estado.caso_ids]
    return jsonify({
        "batch_id": estado.batch_id,
        "total_casos": len(estado.caso_ids),
        "nombres": nombres_lista,
        "generar_cuarto": estado.generar_cuarto,
        "advertencias": estado.advertencias,
        "url_iniciar": url_for("batch_iniciar", batch_id=estado.batch_id),
        "url_cancelar": url_for("batch_cancelar", batch_id=estado.batch_id),
        "url_batch": url_for("pagina_batch_seguimiento", batch_id=estado.batch_id),
    })


@app.route("/batch/<batch_id>/iniciar", methods=["POST"])
def batch_iniciar(batch_id: str):
    """Confirma el preview y encola los casos para procesamiento real."""
    estado = batch.iniciar_batch(batch_id)
    if estado is None:
        return jsonify({"error": "Batch no existe"}), 404
    return jsonify({
        "batch_id": batch_id,
        "url_batch": url_for("pagina_batch_seguimiento", batch_id=batch_id),
    })


@app.route("/batch/<batch_id>/cancelar", methods=["POST"])
def batch_cancelar(batch_id: str):
    """Cancela un batch en preview (marca todos sus casos como error)."""
    estado = batch.cancelar_batch(batch_id)
    if estado is None:
        return jsonify({"error": "Batch no existe"}), 404
    return jsonify({"batch_id": batch_id, "ok": True})


@app.route("/batch/<batch_id>", methods=["GET"])
def pagina_batch_seguimiento(batch_id: str):
    """Página con la tabla de progreso del lote."""
    if batch.cargar_batch(batch_id) is None:
        abort(404)
    return render_template("batch.html", batch_id=batch_id)


@app.route("/batch/<batch_id>/status", methods=["GET"])
def batch_status(batch_id: str):
    """JSON con el estado actual de todos los casos del batch."""
    data = batch.estado_completo_batch(batch_id)
    if data is None:
        return jsonify({"error": "Batch no existe"}), 404
    return jsonify(data)


@app.route("/api/detener-procesos", methods=["POST"])
def api_detener_procesos():
    """Endpoint para el botón 'Detener procesos en curso' de la UI.
    Vacía la cola del worker, mata subprocesos claude hijos, y marca todos
    los casos no terminales como error. El worker queda vivo esperando.
    """
    stats = batch.detener_procesos()
    return jsonify({"ok": True, "stats": stats})


@app.route("/batches", methods=["GET"])
def pagina_historial_batches():
    """Historial de todos los lotes procesados."""
    return render_template("historial_batch.html")


@app.route("/batches/json", methods=["GET"])
def listar_batches_json():
    """JSON con los últimos N batches y sus contadores agregados."""
    return jsonify({"batches": batch.listar_batches(limite=50)})


if __name__ == "__main__":
    # Re-encolar casos huérfanos (que quedaron pendientes por un reinicio).
    n_recuperados = batch.recuperar_pendientes()
    if n_recuperados:
        logging.info("Recuperados %d caso(s) huérfano(s) tras reinicio.", n_recuperados)
    app.run(host="127.0.0.1", port=8000, debug=False)
