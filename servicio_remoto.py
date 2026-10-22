import re
import threading
import time
import uuid

from configuracion import (
    BLOQUEO_LOGIN_SEGUNDOS,
    DURACION_SESION_SEGUNDOS,
    MAX_CANTIDAD_OPERACION,
    MAX_INTENTOS_LOGIN,
)
from seguridad import crear_token, verificar_token


PATRON_USUARIO = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class ServicioInventarioRemoto:
    """Objeto publicado por cada servidor y consumido mediante un proxy remoto."""

    def __init__(self, inventario, servidor_id, secreto_token):
        self.inventario = inventario
        self.servidor_id = servidor_id
        self.secreto_token = secreto_token
        self._lock_login = threading.Lock()
        self._fallos_login = {}

    def ping(self):
        return {
            "exito": True,
            "servidor": self.servidor_id,
            "tipo": "objeto_distribuido",
            "id_objeto": id(self),
        }

    def autenticar(self, usuario, clave):
        usuario = str(usuario or "").strip()
        clave = str(clave or "")
        permitido, espera = self._puede_intentar_login(usuario)
        if not permitido:
            return {
                "exito": False,
                "mensaje": f"Demasiados intentos. Espera {espera} segundos.",
                "servidor": self.servidor_id,
            }

        datos = self.inventario.autenticar_usuario(usuario, clave)
        if datos is None:
            self._registrar_fallo_login(usuario)
            self.inventario.registrar_auditoria(
                usuario or "desconocido",
                "sin_sesion",
                "login",
                "Credenciales rechazadas",
                self.servidor_id,
                False,
            )
            return {
                "exito": False,
                "mensaje": "Usuario o contraseña incorrectos.",
                "servidor": self.servidor_id,
            }

        self._limpiar_fallos(usuario)
        token = crear_token(
            datos["usuario"],
            datos["rol"],
            self.secreto_token,
            DURACION_SESION_SEGUNDOS,
        )
        self.inventario.registrar_auditoria(
            datos["usuario"],
            datos["rol"],
            "login",
            "Sesión iniciada",
            self.servidor_id,
            True,
        )
        return {
            "exito": True,
            "mensaje": "Autenticación correcta.",
            "token": token,
            "usuario": datos["usuario"],
            "rol": datos["rol"],
            "expira_en": DURACION_SESION_SEGUNDOS,
            "servidor": self.servidor_id,
        }

    def listar_inventario(self, token):
        sesion = self._autorizar(token)
        if not sesion["exito"]:
            return sesion
        return self._respuesta(
            True,
            "Inventario consultado.",
            productos=self.inventario.obtener_inventario(),
        )

    def consultar_producto(self, token, id_producto):
        sesion = self._autorizar(token)
        if not sesion["exito"]:
            return sesion
        id_producto = self._normalizar_id_producto(id_producto)
        if id_producto is None:
            return self._respuesta(False, "ID de producto inválido.")
        producto = self.inventario.consultar_producto(id_producto)
        if producto is None:
            return self._respuesta(False, "Producto no encontrado.")
        return self._respuesta(True, "Producto encontrado.", producto=producto)

    def vender(self, token, id_producto, cantidad, request_id=None):
        sesion = self._autorizar(token, roles=("vendedor",))
        if not sesion["exito"]:
            return sesion
        validacion = self._validar_operacion(id_producto, cantidad, request_id)
        if not validacion["exito"]:
            return validacion

        respuesta = self.inventario.vender(
            validacion["id_producto"],
            validacion["cantidad"],
            validacion["request_id"],
            sesion["usuario"],
        )
        self._auditar(sesion, "vender", validacion, respuesta)
        return self._con_servidor(respuesta)

    def agregar_stock(self, token, id_producto, cantidad, request_id=None):
        sesion = self._autorizar(token, roles=("administrador",))
        if not sesion["exito"]:
            return sesion
        validacion = self._validar_operacion(id_producto, cantidad, request_id)
        if not validacion["exito"]:
            return validacion

        respuesta = self.inventario.agregar_stock(
            validacion["id_producto"],
            validacion["cantidad"],
            validacion["request_id"],
            sesion["usuario"],
        )
        self._auditar(sesion, "agregar_stock", validacion, respuesta)
        return self._con_servidor(respuesta)

    def crear_usuario(self, token, usuario_nuevo, clave_nueva, rol_nuevo):
        sesion = self._autorizar(token, roles=("administrador",))
        if not sesion["exito"]:
            return sesion

        usuario_nuevo = str(usuario_nuevo or "").strip()
        rol_nuevo = str(rol_nuevo or "").strip().lower()
        if not PATRON_USUARIO.fullmatch(usuario_nuevo):
            return self._respuesta(
                False,
                "El usuario debe tener entre 3 y 32 caracteres alfanuméricos o . _ -",
            )
        if rol_nuevo not in ("vendedor", "administrador"):
            return self._respuesta(False, "Rol inválido.")
        if len(str(clave_nueva or "")) < 8:
            return self._respuesta(False, "La contraseña debe tener al menos 8 caracteres.")

        creado = self.inventario.crear_usuario(usuario_nuevo, str(clave_nueva), rol_nuevo)
        respuesta = self._respuesta(
            creado,
            "Usuario creado correctamente." if creado else "El usuario ya existe.",
        )
        self.inventario.registrar_auditoria(
            sesion["usuario"],
            sesion["rol"],
            "crear_usuario",
            f"usuario={usuario_nuevo}; rol={rol_nuevo}",
            self.servidor_id,
            creado,
        )
        return respuesta

    def cambiar_clave(self, token, clave_actual, clave_nueva):
        sesion = self._autorizar(token)
        if not sesion["exito"]:
            return sesion
        if len(str(clave_nueva or "")) < 8:
            return self._respuesta(False, "La nueva contraseña debe tener al menos 8 caracteres.")

        exito, mensaje = self.inventario.cambiar_clave(
            sesion["usuario"], str(clave_actual or ""), str(clave_nueva or "")
        )
        self.inventario.registrar_auditoria(
            sesion["usuario"],
            sesion["rol"],
            "cambiar_clave",
            "Cambio de credencial propia",
            self.servidor_id,
            exito,
        )
        return self._respuesta(exito, mensaje)

    def obtener_auditoria(self, token, limite=20):
        sesion = self._autorizar(token, roles=("administrador",))
        if not sesion["exito"]:
            return sesion
        try:
            limite = max(1, min(int(limite), 100))
        except (TypeError, ValueError):
            limite = 20
        return self._respuesta(
            True,
            "Auditoría consultada.",
            registros=self.inventario.obtener_auditoria(limite),
        )

    def _autorizar(self, token, roles=None):
        try:
            payload = verificar_token(str(token or ""), self.secreto_token)
        except ValueError as error:
            return self._respuesta(False, str(error), requiere_login=True)

        usuario = payload["u"]
        rol = payload["r"]
        if not self.inventario.usuario_activo_con_rol(usuario, rol):
            return self._respuesta(False, "La cuenta ya no está autorizada.", requiere_login=True)
        if roles and rol not in roles:
            return self._respuesta(False, "No tienes permisos para ejecutar esta operación.")
        return {"exito": True, "usuario": usuario, "rol": rol}

    def _validar_operacion(self, id_producto, cantidad, request_id):
        id_producto = self._normalizar_id_producto(id_producto)
        if id_producto is None:
            return self._respuesta(False, "ID de producto inválido.")
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            return self._respuesta(False, "Cantidad inválida.")
        if cantidad <= 0 or cantidad > MAX_CANTIDAD_OPERACION:
            return self._respuesta(
                False,
                f"La cantidad debe estar entre 1 y {MAX_CANTIDAD_OPERACION}.",
            )
        request_id = str(request_id or uuid.uuid4())
        if len(request_id) > 80:
            return self._respuesta(False, "request_id inválido.")
        return {
            "exito": True,
            "id_producto": id_producto,
            "cantidad": cantidad,
            "request_id": request_id,
        }

    @staticmethod
    def _normalizar_id_producto(id_producto):
        valor = str(id_producto or "").strip().upper()
        if not re.fullmatch(r"P\d{3}", valor):
            return None
        return valor

    def _respuesta(self, exito, mensaje, **extra):
        respuesta = {
            "exito": bool(exito),
            "mensaje": mensaje,
            "servidor": self.servidor_id,
        }
        respuesta.update(extra)
        return respuesta

    def _con_servidor(self, respuesta):
        copia = dict(respuesta)
        copia["servidor"] = self.servidor_id
        return copia

    def _auditar(self, sesion, accion, datos, respuesta):
        detalle = (
            f"producto={datos['id_producto']}; cantidad={datos['cantidad']}; "
            f"request_id={datos['request_id']}"
        )
        self.inventario.registrar_auditoria(
            sesion["usuario"],
            sesion["rol"],
            accion,
            detalle,
            self.servidor_id,
            respuesta.get("exito", False),
        )

    def _puede_intentar_login(self, usuario):
        ahora = time.monotonic()
        with self._lock_login:
            datos = self._fallos_login.get(usuario)
            if not datos:
                return True, 0
            intentos, bloqueado_hasta = datos
            if bloqueado_hasta and ahora < bloqueado_hasta:
                return False, max(1, int(bloqueado_hasta - ahora))
            if bloqueado_hasta and ahora >= bloqueado_hasta:
                self._fallos_login.pop(usuario, None)
            return True, 0

    def _registrar_fallo_login(self, usuario):
        ahora = time.monotonic()
        with self._lock_login:
            intentos, bloqueado_hasta = self._fallos_login.get(usuario, (0, 0.0))
            if bloqueado_hasta and ahora >= bloqueado_hasta:
                intentos = 0
            intentos += 1
            if intentos >= MAX_INTENTOS_LOGIN:
                bloqueado_hasta = ahora + BLOQUEO_LOGIN_SEGUNDOS
                intentos = 0
            self._fallos_login[usuario] = (intentos, bloqueado_hasta)

    def _limpiar_fallos(self, usuario):
        with self._lock_login:
            self._fallos_login.pop(usuario, None)
