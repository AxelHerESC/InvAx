from functools import wraps
from pathlib import Path
import re
from uuid import UUID

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from backend.conexion import ClusterNoDisponible, ConexionCluster


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def create_app(servidores=None, authkey=None):
    app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="/assets")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    cluster = ConexionCluster(servidores, authkey)

    @app.after_request
    def proteger_respuesta(respuesta):
        respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "same-origin"
        respuesta.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
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

    def autenticada(funcion):
        @wraps(funcion)
        def ejecutar(*args, **kwargs):
            esquema, _, token = request.headers.get("Authorization", "").partition(" ")
            if esquema.lower() != "bearer" or not token or not token.isascii() or len(token) > 4096:
                return jsonify(exito=False, mensaje="Inicia sesión para continuar.", requiere_login=True), 401
            g.token = token
            return funcion(*args, **kwargs)
        return ejecutar

    def responder(resultado, exito=200, fallo=400):
        if resultado.get("requiere_login"):
            codigo = 401
        elif resultado.get("codigo") == "SIN_PERMISOS":
            codigo = 403
        else:
            codigo = exito if resultado["exito"] else fallo
        return jsonify(resultado), codigo

    def cuerpo_json():
        datos = request.get_json()
        if not isinstance(datos, dict):
            from werkzeug.exceptions import BadRequest
            raise BadRequest("Envía un objeto JSON.")
        return datos

    def texto_valido(valor, minimo=1, maximo=256):
        return isinstance(valor, str) and minimo <= len(valor) <= maximo and not any(0xD800 <= ord(c) <= 0xDFFF for c in valor)

    @app.get("/")
    def inicio():
        return send_from_directory(FRONTEND, "index.html")

    @app.get("/api/salud")
    def salud():
        return jsonify(exito=True, servicio="InvAx", etapa=3, mensaje="Backend HTTP activo.")

    @app.get("/api/listo")
    def listo():
        resultado = cluster.invocar("comprobar_disponibilidad")
        return responder(resultado, fallo=503)

    @app.post("/api/login")
    def login():
        datos = cuerpo_json()
        usuario, clave = datos.get("usuario"), datos.get("clave")
        if not texto_valido(usuario, maximo=32) or not usuario.strip() or not texto_valido(clave):
            return jsonify(exito=False, mensaje="Escribe un usuario válido y su contraseña."), 400
        return responder(cluster.invocar("autenticar", usuario, clave), fallo=401)

    @app.get("/api/sesion")
    @autenticada
    def sesion():
        return responder(cluster.invocar("obtener_sesion", g.token), fallo=401)

    @app.get("/api/productos")
    @autenticada
    def productos():
        return responder(cluster.invocar("listar_inventario", g.token), fallo=401)

    @app.get("/api/productos/<id_producto>")
    @autenticada
    def producto(id_producto):
        if not re.fullmatch(r"P\d{3}", id_producto.upper()):
            return jsonify(exito=False, mensaje="ID de producto inválido."), 400
        return responder(cluster.invocar("consultar_producto", g.token, id_producto), fallo=404)

    def movimiento(metodo):
        datos = cuerpo_json()
        producto, cantidad, request_id = datos.get("id_producto"), datos.get("cantidad"), datos.get("request_id")
        if not texto_valido(producto, maximo=16) or type(cantidad) is not int or not 1 <= cantidad <= 10000:
            return jsonify(exito=False, mensaje="Selecciona un producto y una cantidad entera entre 1 y 10000."), 400
        try:
            if not isinstance(request_id, str) or len(request_id) > 80:
                raise ValueError
            request_id = str(UUID(request_id))
        except (ValueError, AttributeError):
            return jsonify(exito=False, mensaje="La operación requiere un request_id UUID válido."), 400
        return responder(cluster.invocar(metodo, g.token, producto, cantidad, request_id), fallo=409)

    @app.post("/api/ventas")
    @autenticada
    def vender():
        return movimiento("vender")

    @app.post("/api/reposiciones")
    @autenticada
    def reponer():
        return movimiento("agregar_stock")

    @app.post("/api/usuarios")
    @autenticada
    def crear_usuario():
        datos = cuerpo_json()
        usuario, clave, rol = datos.get("usuario"), datos.get("clave"), datos.get("rol")
        if not texto_valido(usuario, 3, 32) or not texto_valido(clave, 8) or rol not in ("vendedor", "administrador"):
            return jsonify(exito=False, mensaje="Escribe un usuario de 3 a 32 caracteres, una contraseña de 8 a 256 caracteres y un rol válido."), 400
        return responder(cluster.invocar("crear_usuario", g.token, usuario, clave, rol), exito=201, fallo=409)

    @app.put("/api/clave")
    @autenticada
    def cambiar_clave():
        datos = cuerpo_json()
        actual, nueva = datos.get("clave_actual"), datos.get("clave_nueva")
        if not texto_valido(actual) or not texto_valido(nueva, 8):
            return jsonify(exito=False, mensaje="La nueva contraseña debe tener entre 8 y 256 caracteres."), 400
        return responder(cluster.invocar("cambiar_clave", g.token, actual, nueva))

    @app.get("/api/auditoria")
    @autenticada
    def auditoria():
        try:
            limite = int(request.args.get("limite", "30"))
            if not 1 <= limite <= 100:
                raise ValueError
        except ValueError:
            return jsonify(exito=False, mensaje="El límite debe estar entre 1 y 100."), 400
        return responder(cluster.invocar("obtener_auditoria", g.token, limite))

    @app.get("/api/servidores")
    @autenticada
    def estado_servidores():
        resultado = cluster.invocar("obtener_sesion", g.token)
        if not resultado["exito"]:
            return responder(resultado, fallo=401)
        return jsonify(exito=True, servidores=cluster.estado())

    return app
