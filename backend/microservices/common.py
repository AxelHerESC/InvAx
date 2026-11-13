"""Transporte, errores, trazas y autenticación interna compartidos."""
import hmac
import json
import logging
import os
import re
import time
from uuid import uuid4
from urllib.parse import urlsplit

from flask import Flask, g, has_request_context, jsonify, request
import requests
from werkzeug.exceptions import HTTPException

from backend.conexion import ClusterNoDisponible
from inventario_postgres import AlmacenNoDisponible

LOG = logging.getLogger("invax.http")
SERVICES = ("auth", "productos", "ventas", "reposiciones")


class ServiceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def trace_id():
    return g.request_id if has_request_context() and hasattr(g, "request_id") else str(uuid4())


def install_observability(app, name):
    @app.before_request
    def start_request():
        value = request.headers.get("X-Request-ID", "")
        g.request_id = value if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) else str(uuid4())
        g.started = time.monotonic()

    @app.after_request
    def finish_request(response):
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Cache-Control"] = "no-store"
        LOG.info(json.dumps({"request_id": g.request_id, "servicio": name,
                             "origen": request.headers.get("X-Caller-Service") if request.headers.get("X-Caller-Service") in (*SERVICES, "gateway") else "cliente",
                             "metodo": request.method, "ruta": request.path,
                             "estado": response.status_code,
                             "ms": round((time.monotonic()-g.started)*1000)}))
        return response

    @app.errorhandler(ServiceError)
    def dependency_error(error):
        return jsonify(exito=False, mensaje=error.message), error.status

    @app.errorhandler(AlmacenNoDisponible)
    def database_error(error):
        return jsonify(exito=False, mensaje="La persistencia no está disponible temporalmente."), 503

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(exito=False, mensaje=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # No imprimir cuerpos, cabeceras, credenciales ni textos SQL.
        LOG.error(json.dumps({"request_id": trace_id(), "servicio": name, "error": type(error).__name__}))
        return jsonify(exito=False, mensaje="Error interno del servicio."), 500


def internal_app(name, cluster_token, methods):
    if not cluster_token or len(cluster_token) < 32:
        raise RuntimeError("Configura INVAX_CLUSTER_TOKEN con al menos 32 caracteres.")
    app = Flask("invax-"+name, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16*1024
    install_observability(app, name)

    @app.get("/api/health")
    def health():
        return jsonify(exito=True, servicio=name)

    @app.post("/internal/rpc")
    def rpc():
        provided = request.headers.get("X-Cluster-Token", "")
        if not provided.isascii() or not hmac.compare_digest(provided, cluster_token):
            return jsonify(exito=False, mensaje="Credencial interna inválida."), 401
        data = request.get_json()
        if not isinstance(data, dict) or set(data) != {"method", "args"} or not isinstance(data["method"], str) or not isinstance(data["args"], list):
            return jsonify(exito=False, mensaje="Solicitud RPC inválida."), 400
        function = methods.get(data["method"])
        if function is None:
            return jsonify(exito=False, mensaje="Operación no publicada por este servicio."), 404
        import inspect
        try:
            inspect.signature(function).bind(*data["args"])
        except TypeError:
            return jsonify(exito=False, mensaje="Argumentos RPC inválidos."), 400
        result = function(*data["args"])
        if isinstance(result, tuple):
            body, status = result
        else:
            body, status = result, result_status(result)
        return jsonify(body), status

    return app


def result_status(result):
    if result.get("requiere_login"):
        return 401
    if result.get("codigo") == "SIN_PERMISOS":
        return 403
    return 200 if result.get("exito") else 400


class HttpClient:
    """Una petición por llamada: no repite automáticamente escrituras ni sigue redirects."""
    def __init__(self, urls, cluster_token, caller, connect_timeout=1.5, read_timeout=None):
        self.urls, self.token, self.caller = urls, cluster_token, caller
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        if not cluster_token or len(cluster_token) < 32:
            raise RuntimeError("INVAX_CLUSTER_TOKEN es obligatorio.")
        for name, url in urls.items():
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
                raise RuntimeError("Dirección de servicio inválida: "+name)

    def call(self, service, method, args, *, request_id=None):
        if service not in self.urls:
            raise ServiceError(503, "Dependencia no configurada: "+service)
        started = time.monotonic()
        rid = request_id or trace_id()
        try:
            # trust_env=False: no enviar credenciales de clúster a proxies del entorno.
            with requests.Session() as session:
                session.trust_env = False
                timeout = self.read_timeout or {"auth": 10, "productos": 15, "ventas": 20, "reposiciones": 20}[service]
                with session.post(self.urls[service].rstrip('/')+"/internal/rpc", json={"method": method, "args": args},
                                  headers={"X-Cluster-Token": self.token, "X-Request-ID": rid,
                                           "X-Caller-Service": self.caller},
                                  timeout=(self.connect_timeout, timeout), allow_redirects=False, stream=True) as response:
                    # Catálogo grande permitido; lectura acotada frente a respuestas ajenas.
                    data = bytearray()
                    for chunk in response.iter_content(65536):
                        data.extend(chunk)
                        if len(data) > 8*1024*1024 or time.monotonic()-started > timeout+2:
                            raise ServiceError(503, "Respuesta de dependencia fuera de límites: "+service)
                    body = json.loads(data)
                    if not isinstance(body, dict) or not isinstance(body.get("exito"), bool) or response.status_code not in (200, 201, 400, 401, 403, 404, 409, 422, 500, 503):
                        raise ValueError("Respuesta RPC inválida")
                    LOG.info(json.dumps({"request_id": rid, "origen": self.caller, "destino": service,
                                         "operacion": method, "estado": response.status_code}))
                    if response.status_code >= 500:
                        raise ServiceError(503, "Dependencia no disponible: "+service)
                    return body, response.status_code
        except ServiceError:
            raise
        except (requests.RequestException, ValueError, TypeError):
            LOG.warning(json.dumps({"request_id": rid, "origen": self.caller, "destino": service, "operacion": method, "estado": 503}))
            raise ServiceError(503, "No fue posible contactar el servicio "+service+".") from None


def authorize(client, token, roles=None):
    if not isinstance(token, str) or not token.isascii() or not 1 <= len(token) <= 4096:
        raise ServiceError(401, "Sesión inválida.")
    body, status = client.call("auth", "obtener_sesion", [token])
    if status != 200:
        raise ServiceError(status, body.get("mensaje", "Sesión inválida."))
    if roles and body["rol"] not in roles:
        raise ServiceError(403, "No tienes permisos para ejecutar esta operación.")
    return body


def service_urls():
    return {name: os.environ[name.upper()+"_URL"] for name in SERVICES if os.environ.get(name.upper()+"_URL")}
