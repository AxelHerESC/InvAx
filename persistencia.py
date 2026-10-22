import os

from inventario import InventarioDistribuido


def crear_inventario(ruta_sqlite):
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        from inventario_postgres import InventarioPostgres
        return InventarioPostgres(database_url)
    return InventarioDistribuido(ruta_sqlite)
