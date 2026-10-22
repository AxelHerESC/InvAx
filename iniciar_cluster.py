import os
import signal
import subprocess
import sys
import time

from configuracion import (
    CLAVE_ADMIN_INICIAL,
    CLAVE_VENDEDOR_INICIAL,
    RUTA_BD,
    SERVIDORES,
    preparar_secretos,
)


def main():
    carpeta = os.path.dirname(os.path.abspath(__file__))
    servidor_py = os.path.join(carpeta, "servidor.py")
    preparar_secretos()
    procesos = []

    print("Iniciando cluster de objetos distribuidos...")
    for servidor_id, host, puerto in SERVIDORES:
        proceso = subprocess.Popen(
            [
                sys.executable,
                servidor_py,
                "--id",
                servidor_id,
                "--host",
                host,
                "--puerto",
                str(puerto),
                "--bd",
                str(RUTA_BD),
            ],
            cwd=carpeta,
        )
        procesos.append(proceso)
        print(f"{servidor_id} iniciado en {host}:{puerto} (PID {proceso.pid})")
        time.sleep(0.25)

    print("\nCluster activo. Ejecuta cliente.py en una o varias terminales.")
    print("Credenciales iniciales de demostración:")
    print(f"  Administrador -> admin / {CLAVE_ADMIN_INICIAL}")
    print(f"  Vendedor      -> vendedor / {CLAVE_VENDEDOR_INICIAL}")
    print("Cambia las contraseñas desde el cliente después del primer acceso.")
    print("Presiona Ctrl+C aquí para detener todos los servidores.\n")

    try:
        for proceso in procesos:
            proceso.wait()
    except KeyboardInterrupt:
        print("\nDeteniendo cluster...")
        for proceso in procesos:
            if proceso.poll() is None:
                if os.name == "nt":
                    proceso.terminate()
                else:
                    proceso.send_signal(signal.SIGTERM)
        for proceso in procesos:
            try:
                proceso.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proceso.kill()


if __name__ == "__main__":
    main()
