from pathlib import Path
import socket
import sys
import uvicorn


BASE_DIR = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
PORT = 8000

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import app


def _ensure_port_available() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, PORT))
        except OSError:
            print("\n")
            print(f"  El puerto {PORT} ya esta en uso.")
            print("  Cierra el servidor anterior o usa otro puerto antes de arrancar la app.")
            print("\n")
            raise SystemExit(1)


if __name__ == "__main__":
    _ensure_port_available()

    print("\n")
    print("  Puerto libre - arrancando servidor")
    print(f"  Abre la app aqui: http://{HOST}:{PORT}")
    print("      (Ctrl+Click para abrir en el navegador)")
    print("\n")

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
