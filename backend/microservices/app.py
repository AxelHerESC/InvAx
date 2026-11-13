"""Selección explícita del proceso; cada contenedor construye una sola aplicación."""
import logging
import os
from backend.microservices.common import HttpClient, service_urls
from backend.microservices.gateway import create_gateway
from backend.microservices.services import create_auth, create_products, create_movements
from backend.microservices.stores import AuthStore, ProductStore


def create_app():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    name = os.environ.get("INVAX_SERVICE", "gateway")
    token = os.environ.get("INVAX_CLUSTER_TOKEN", "")
    client = HttpClient(service_urls(), token, name)
    if name == "gateway":
        return create_gateway(client)
    if name in ("ventas", "reposiciones"):
        return create_movements(name, client, token)
    if name not in ("auth", "productos"):
        raise RuntimeError("INVAX_SERVICE no reconocido.")
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL es obligatorio para el propietario de datos.")
    if name == "productos":
        return create_products(ProductStore(url), client, token)
    secret = os.environ.get("INVENTARIO_TOKEN_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("Configura INVENTARIO_TOKEN_SECRET; conserva el secreto de P07.")
    store = AuthStore(url)
    if store.obtener_usuario("admin") is None:
        admin, seller = os.environ.get("INVENTARIO_ADMIN_PASSWORD", ""), os.environ.get("INVENTARIO_VENDEDOR_PASSWORD", "")
        if min(len(admin), len(seller)) < 12 or admin == seller:
            raise RuntimeError("Se requieren contraseñas iniciales distintas de al menos 12 caracteres para una base nueva.")
        store.asegurar_usuarios_iniciales(admin, seller)
    return create_auth(store, secret.encode(), token)
