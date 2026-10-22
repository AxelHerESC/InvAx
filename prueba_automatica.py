import os
import subprocess
import sys
import time
from pathlib import Path

from cliente import ClienteObjetosDistribuidos
from configuracion import RUTA_BD, preparar_secretos


BASE = Path(__file__).resolve().parent


def main():
    preparar_secretos()
    procesos = []
    try:
        for servidor_id, puerto in [("T1", 5200), ("T2", 5201)]:
            proceso = subprocess.Popen(
                [
                    sys.executable,
                    str(BASE / "servidor.py"),
                    "--id",
                    servidor_id,
                    "--puerto",
                    str(puerto),
                    "--bd",
                    str(BASE / "prueba_inventario.db"),
                ],
                cwd=str(BASE),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            procesos.append(proceso)
        time.sleep(1.2)

        servidores = [("T1", "127.0.0.1", 5200), ("T2", "127.0.0.1", 5201)]
        cliente = ClienteObjetosDistribuidos(servidores)
        cliente.conectar()
        r = cliente.iniciar_sesion("vendedor", "Venta2026!")
        assert r["exito"], r
        r = cliente.listar_inventario()
        assert r["exito"] and len(r["productos"]) >= 4, r
        r = cliente.vender("P002", 1)
        assert r["exito"], r

        cliente_admin = ClienteObjetosDistribuidos(servidores)
        cliente_admin.conectar()
        r = cliente_admin.iniciar_sesion("admin", "Admin2026!")
        assert r["exito"], r
        r = cliente_admin.agregar_stock("P002", 1)
        assert r["exito"], r
        r = cliente_admin.obtener_auditoria(10)
        assert r["exito"] and r["registros"], r

        print("PRUEBA OK: autenticación, proxy remoto, venta, stock y auditoría.")
    finally:
        for proceso in procesos:
            if proceso.poll() is None:
                proceso.terminate()
        for proceso in procesos:
            try:
                proceso.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proceso.kill()
        for nombre in ("prueba_inventario.db", "prueba_inventario.db-wal", "prueba_inventario.db-shm"):
            ruta = BASE / nombre
            if ruta.exists():
                ruta.unlink()


if __name__ == "__main__":
    main()
