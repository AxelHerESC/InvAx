"""Inicia los objetos internos y la API pública en un único servidor Linux."""
import os
import signal
import subprocess
import sys
import time

from backend.conexion import GestorInventario
from configuracion import DATA_DIR, RUTA_BD, SERVIDORES, preparar_secretos


def esperar_nodo(proceso, host, puerto, authkey):
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            raise RuntimeError("Un nodo del inventario terminó durante el arranque.")
        try:
            gestor = GestorInventario(address=(host, puerto), authkey=authkey)
            gestor.connect()
            gestor.obtener_servicio_inventario().ping()
            return
        except (OSError, EOFError):
            time.sleep(0.2)
    raise RuntimeError("El nodo no estuvo disponible dentro del plazo de arranque.")


def main():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("Configura DATABASE_URL con la conexión PostgreSQL de Supabase.")
    if not os.environ.get("INVENTARIO_AUTHKEY") or not os.environ.get("INVENTARIO_TOKEN_SECRET"):
        raise RuntimeError("Configura INVENTARIO_AUTHKEY e INVENTARIO_TOKEN_SECRET como secretos del alojamiento.")
    for nombre, predeterminada in (
        ("INVENTARIO_ADMIN_PASSWORD", "Admin2026!"),
        ("INVENTARIO_VENDEDOR_PASSWORD", "Venta2026!"),
    ):
        valor = os.environ.get(nombre, "")
        if len(valor) < 12 or valor == predeterminada:
            raise RuntimeError(f"Configura {nombre} con una contraseña propia de al menos 12 caracteres.")
    if os.environ["INVENTARIO_ADMIN_PASSWORD"] == os.environ["INVENTARIO_VENDEDOR_PASSWORD"]:
        raise RuntimeError("Las contraseñas iniciales deben ser distintas.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secretos = preparar_secretos()
    procesos = []

    def detener(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, detener)
    signal.signal(signal.SIGINT, detener)
    try:
        for servidor_id, host, puerto in SERVIDORES:
            proceso = subprocess.Popen([
                sys.executable, "servidor.py", "--id", servidor_id,
                "--host", host, "--puerto", str(puerto), "--bd", str(RUTA_BD),
            ])
            procesos.append(proceso)
            esperar_nodo(proceso, host, puerto, secretos["authkey"])

        puerto_http = int(os.environ.get("PORT", "8080"))
        if not 1 <= puerto_http <= 65535:
            raise RuntimeError("PORT debe estar entre 1 y 65535.")
        procesos.append(subprocess.Popen([
            sys.executable, "-m", "gunicorn", "backend.app:create_app()",
            "--bind", f"0.0.0.0:{puerto_http}", "--workers", "1",
            "--threads", "4", "--timeout", "45", "--access-logfile", "-",
        ]))
        print("InvAx: objetos internos activos. API HTTP iniciando.", flush=True)
        while True:
            for proceso in procesos:
                if proceso.poll() is not None:
                    raise RuntimeError("Un proceso del servicio se detuvo; se requiere reinicio.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proceso in reversed(procesos):
            if proceso.poll() is None:
                proceso.terminate()
        for proceso in reversed(procesos):
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait()


if __name__ == "__main__":
    main()
