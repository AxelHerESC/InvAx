import argparse
from multiprocessing.managers import BaseManager

from configuracion import (
    CLAVE_ADMIN_INICIAL,
    CLAVE_VENDEDOR_INICIAL,
    RUTA_BD,
    cargar_secretos_servidor,
)
from inventario import InventarioDistribuido
from servicio_remoto import ServicioInventarioRemoto


_SERVICIO = None


def obtener_servicio_inventario():
    return _SERVICIO


class GestorInventario(BaseManager):
    pass


def leer_argumentos():
    parser = argparse.ArgumentParser(
        description="Servidor de objeto distribuido para el sistema de inventario"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=5100)
    parser.add_argument("--id", dest="servidor_id", default="S1")
    parser.add_argument("--bd", default=str(RUTA_BD))
    return parser.parse_args()


def main():
    global _SERVICIO
    args = leer_argumentos()
    secretos = cargar_secretos_servidor()

    inventario = InventarioDistribuido(args.bd)
    nuevos = inventario.asegurar_usuarios_iniciales(
        CLAVE_ADMIN_INICIAL, CLAVE_VENDEDOR_INICIAL
    )
    _SERVICIO = ServicioInventarioRemoto(
        inventario, args.servidor_id, secretos["token_secret"]
    )

    GestorInventario.register(
        "obtener_servicio_inventario",
        callable=obtener_servicio_inventario,
    )
    gestor = GestorInventario(
        address=(args.host, args.puerto),
        authkey=secretos["authkey"],
    )
    servidor = gestor.get_server()

    print("=" * 76)
    print("SERVIDOR - OBJETO DISTRIBUIDO DE INVENTARIO")
    print("=" * 76)
    print(f"ID: {args.servidor_id}")
    print(f"Dirección: {args.host}:{args.puerto}")
    print("Objeto publicado: ServicioInventarioRemoto")
    print("Invocación: proxy de multiprocessing.managers.BaseManager")
    print("Persistencia compartida: SQLite WAL")
    print("Seguridad: authkey + PBKDF2 + tokens HMAC + RBAC + auditoría")
    if nuevos:
        print("Usuarios iniciales creados en la base de datos.")
    print("Ctrl+C para detener el servidor.")

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{args.servidor_id}] Servidor detenido.")


if __name__ == "__main__":
    main()
