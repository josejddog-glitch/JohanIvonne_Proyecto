"""Punto de entrada para PyInstaller.

Hace lo mismo que `run.bat` pero como un proceso Python único:
  1. Arranca Flask en un thread.
  2. Abre el navegador en http://localhost:8000.
  3. Mantiene viva la app hasta que se cierra la ventana de consola
     (cuando se compila como --noconsole, queda en background).
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resource_dir() -> Path:
    """Directorio donde están los recursos (templates/, knowledge/, etc.).

    En modo PyInstaller los recursos se extraen a sys._MEIPASS. En desarrollo,
    es el directorio del propio launcher.
    """
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


def main() -> None:
    base = _resource_dir()
    os.chdir(base)
    sys.path.insert(0, str(base))

    import app as flask_app  # noqa: E402

    def _serve():
        flask_app.app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)

    t = threading.Thread(target=_serve, name="flask-server", daemon=True)
    t.start()

    time.sleep(1.5)
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    # Mantener vivo el proceso principal.
    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
