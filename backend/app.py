from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.conexion import ClusterNoDisponible, ConexionCluster


def create_app(servidores=None, authkey=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    cluster = ConexionCluster(servidores, authkey)

    @app.after_request
    def proteger_respuesta(respuesta):
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        return respuesta

    @app.errorhandler(ClusterNoDisponible)
    def cluster_no_disponible(error):
        return jsonify(exito=False, mensaje="El inventario no está disponible temporalmente. Intenta nuevamente."), 503

    @app.errorhandler(HTTPException)
    def error_http(error):
        respuesta = error.get_response()
        respuesta.data = app.json.dumps({"exito": False, "mensaje": error.description})
        respuesta.content_type = "application/json"
        return respuesta

    def token_solicitud():
        esquema, _, token = request.headers.get("Authorization", "").partition(" ")
        if esquema.lower() != "bearer" or not token or not token.isascii() or len(token) > 4096:
            return None
        return token

    @app.get("/api/salud")
    def salud():
        return jsonify(exito=True, servicio="InvAx", etapa=2,
                       mensaje="Backend HTTP activo. Esta ruta no comprueba el cluster.")

    @app.get("/api/listo")
    def listo():
        resultado = cluster.invocar("comprobar_disponibilidad")
        return jsonify(resultado), 200 if resultado["exito"] else 503

    @app.post("/api/login")
    def login():
        datos = request.get_json()
        if not isinstance(datos, dict):
            return jsonify(exito=False, mensaje="Envía un objeto JSON."), 400
        usuario, clave = datos.get("usuario"), datos.get("clave")
        if not isinstance(usuario, str) or not isinstance(clave, str) or not usuario.strip() or not clave:
            return jsonify(exito=False, mensaje="Usuario y clave son obligatorios y deben ser texto."), 400
        if len(usuario) > 32 or len(clave) > 256:
            return jsonify(exito=False, mensaje="Usuario o clave exceden la longitud permitida."), 400
        resultado = cluster.invocar("autenticar", usuario, clave)
        return jsonify(resultado), 200 if resultado["exito"] else 401

    @app.get("/api/productos")
    def productos():
        token = token_solicitud()
        if token is None:
            return jsonify(exito=False, mensaje="Envía Authorization: Bearer <token>.", requiere_login=True), 401
        resultado = cluster.invocar("listar_inventario", token)
        return jsonify(resultado), 200 if resultado["exito"] else 401

    return app
