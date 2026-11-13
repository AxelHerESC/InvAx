"""Adaptador de los contratos REST existentes a RPC HTTP con destinos fijos."""
from backend.app import create_app as public_app
from backend.microservices.common import HttpClient, SERVICES, install_observability, trace_id

DESTINATIONS = {
    "autenticar": "auth", "obtener_sesion": "auth", "crear_usuario": "auth",
    "cambiar_clave": "auth", "obtener_auditoria": "auth",
    "listar_inventario": "productos", "consultar_producto": "productos",
    "comprobar_disponibilidad": "productos", "crear_producto": "productos",
    "editar_producto": "productos", "eliminar_producto": "productos",
    "vender": "ventas", "listar_ventas": "ventas",
    "agregar_stock": "reposiciones", "listar_reposiciones": "reposiciones",
}


class GatewayRouter:
    def __init__(self, client):
        self.client = client

    def invocar(self, method, *args):
        body, status = self.client.call(DESTINATIONS[method], method, list(args))
        return {**body, "_http_status": status}

    def estado(self):
        from concurrent.futures import ThreadPoolExecutor
        from backend.microservices.common import ServiceError
        request_id = trace_id()
        def check(name):
            try:
                # Un diagnóstico breve evita sumar todos los timeouts de negocio.
                diagnostic = HttpClient(self.client.urls, self.client.token, "gateway", connect_timeout=.5, read_timeout=2)
                _, status = diagnostic.call(name, "ping", [], request_id=request_id)
                return {"servidor": name, "disponible": status == 200}
            except ServiceError:
                return {"servidor": name, "disponible": False}
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(check, SERVICES))


def create_gateway(client):
    app = public_app(cluster=GatewayRouter(client))
    install_observability(app, "gateway")
    app.config["INVAX_MICROSERVICES"] = True
    import os
    from flask import request
    origins = {value.strip() for value in os.environ.get("INVAX_ALLOWED_ORIGINS", "").split(",") if value.strip()}
    if "*" in origins:
        raise RuntimeError("Configura orígenes CORS explícitos, sin comodines.")

    @app.after_request
    def cors(response):
        origin = request.headers.get("Origin")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Request-ID"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        return response

    return app
