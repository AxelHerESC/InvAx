import hashlib
import json
import os
from contextlib import contextmanager

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from inventario import InventarioDistribuido
from seguridad import crear_hash_clave, verificar_clave


class AlmacenNoDisponible(Exception):
    """Error de persistencia sin exponer credenciales ni detalles de conexión."""


def diagnostico_postgres(error):
    """Clasifica el error sin devolver su texto, consultas ni credenciales."""
    estado = error.sqlstate
    texto = str(error).lower()
    if "tenant or user not found" in texto:
        return "PG_POOLER: el host o el usuario no corresponden al proyecto. Copia nuevamente el URI de Session pooler desde Supabase."
    if estado == "28P01" or "password authentication failed" in texto or "sasl authentication failed" in texto:
        return "PG_AUTH: PostgreSQL rechazó las credenciales. Revisa la contraseña de la base y su codificación en DATABASE_URL."
    if estado == "28000":
        return "PG_AUTH: PostgreSQL rechazó la autorización de conexión. Revisa usuario, permisos y configuración de red."
    if "could not translate host name" in texto or "failed to resolve" in texto or "name or service not known" in texto:
        return "PG_DNS: no se pudo resolver el servidor de DATABASE_URL. Revisa el host del pooler."
    if "ssl" in texto or "certificate" in texto or "tls" in texto:
        return "PG_TLS: no se pudo establecer la conexión cifrada. Revisa la configuración TLS de PostgreSQL."
    if estado == "55P03":
        return "PG_LOCK: se agotó el tiempo de espera de un bloqueo en PostgreSQL."
    if estado == "57014":
        return "PG_QUERY_TIMEOUT: PostgreSQL canceló la consulta o se agotó su tiempo de ejecución."
    if "timeout" in texto or "timed out" in texto or "timeout expired" in texto:
        return "PG_TIMEOUT: se agotó el tiempo de conexión. Comprueba que Supabase esté activo y que DATABASE_URL use el Session pooler correcto."
    if estado == "42P01":
        return "PG_TABLA: falta una tabla de InvAx. Comprueba el script de tablas en el mismo proyecto de Supabase."
    if estado == "42703":
        return "PG_COLUMNA: las columnas de PostgreSQL no coinciden con las tablas esperadas por InvAx."
    if estado == "42501":
        return "PG_PERMISOS: el usuario de conexión no tiene permisos suficientes sobre las tablas."
    if estado == "53300" or "max client connections" in texto:
        return "PG_LIMITE: se alcanzó el límite de conexiones de PostgreSQL o del pooler."
    if isinstance(error, psycopg.OperationalError):
        return "PG_CONEXION: PostgreSQL no pudo completar la conexión u operación. Revisa el estado de Supabase y su acceso por red."
    if estado and len(estado) == 5 and estado.isalnum():
        return f"PG_ERROR: PostgreSQL devolvió SQLSTATE {estado}."
    return "PG_ERROR: PostgreSQL rechazó la configuración u operación. Revisa el URI y las tablas de InvAx."


def validar_database_url(database_url, database_password=None):
    if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgres://")):
        raise AlmacenNoDisponible("PG_CONFIG: DATABASE_URL debe contener únicamente un URI PostgreSQL, sin comillas ni el prefijo DATABASE_URL=.")
    try:
        parametros = conninfo_to_dict(database_url)
    except psycopg.Error:
        raise AlmacenNoDisponible("PG_CONFIG: el URI de DATABASE_URL no es válido. Comprueba la codificación de caracteres especiales en la contraseña.") from None
    if not all(parametros.get(campo) for campo in ("host", "user", "dbname")):
        raise AlmacenNoDisponible("PG_CONFIG: faltan host, usuario o base de datos en DATABASE_URL.")
    if not database_password and not parametros.get("password"):
        raise AlmacenNoDisponible("PG_CONFIG: configura DATABASE_PASSWORD con la contraseña original de PostgreSQL, sin codificar.")
    if not database_password and parametros.get("password") == "[YOUR-PASSWORD]":
        raise AlmacenNoDisponible("PG_CONFIG: reemplaza [YOUR-PASSWORD], incluidos los corchetes, por la contraseña codificada de la base de datos.")


class InventarioPostgres(InventarioDistribuido):
    """Inventario compartido mediante transacciones PostgreSQL."""

    def __init__(self, database_url):
        self.database_password = os.environ.get("DATABASE_PASSWORD")
        validar_database_url(database_url, self.database_password)
        self.database_url = database_url
        self.verificar_esquema()

    @contextmanager
    def _conectar(self):
        opciones = {}
        password = getattr(self, "database_password", None)
        if password:
            opciones["password"] = password
        try:
            with psycopg.connect(
                self.database_url, row_factory=dict_row, connect_timeout=8,
                sslmode="require", prepare_threshold=None,
                **opciones,
            ) as conexion:
                conexion.execute("SET LOCAL lock_timeout = '4s'")
                conexion.execute("SET LOCAL statement_timeout = '8s'")
                yield conexion
        except psycopg.errors.UniqueViolation:
            raise
        except psycopg.Error as error:
            raise AlmacenNoDisponible(diagnostico_postgres(error)) from None

    @contextmanager
    def _transaccion_escritura(self):
        with self._conectar() as conexion:
            yield conexion

    def verificar_esquema(self):
        with self._conectar() as conexion:
            conexion.execute("SELECT id_producto, nombre, precio, cantidad, version FROM public.productos LIMIT 0")
            conexion.execute("SELECT usuario, salt, clave_hash, rol, activo FROM public.usuarios LIMIT 0")
            conexion.execute("SELECT request_id, accion, usuario, respuesta_json FROM public.operaciones LIMIT 0")
            conexion.execute("SELECT id, usuario, rol, accion, detalle, servidor, exito, creado_en FROM public.auditoria LIMIT 0")

    @staticmethod
    def _bloquear_solicitud(conexion, identificador):
        clave = int.from_bytes(
            hashlib.blake2b(identificador.encode("utf-8"), digest_size=8).digest(),
            "big", signed=True,
        )
        conexion.execute("SELECT pg_advisory_xact_lock(%s)", (clave,))

    @staticmethod
    def _fila_a_producto(fila):
        if fila is None:
            return None
        return {
            "id": fila["id_producto"], "nombre": fila["nombre"],
            "precio": float(fila["precio"]), "cantidad": fila["cantidad"],
            "version": fila["version"],
        }

    def obtener_inventario(self):
        with self._conectar() as conexion:
            filas = conexion.execute("SELECT id_producto, nombre, precio, cantidad, version FROM public.productos ORDER BY id_producto").fetchall()
            return [self._fila_a_producto(fila) for fila in filas]

    def consultar_producto(self, id_producto):
        with self._conectar() as conexion:
            fila = conexion.execute("SELECT id_producto, nombre, precio, cantidad, version FROM public.productos WHERE id_producto = %s", (id_producto,)).fetchone()
            return self._fila_a_producto(fila)

    def obtener_usuario(self, usuario):
        with self._conectar() as conexion:
            return conexion.execute("SELECT usuario, salt, clave_hash, rol, activo FROM public.usuarios WHERE usuario = %s", (usuario,)).fetchone()

    def asegurar_usuarios_iniciales(self, admin_clave, vendedor_clave):
        with self._transaccion_escritura() as conexion:
            self._bloquear_solicitud(conexion, "invax:crear_usuarios_iniciales")
            if conexion.execute("SELECT 1 FROM public.usuarios LIMIT 1").fetchone():
                return False
            for usuario, clave, rol in (
                ("admin", admin_clave, "administrador"),
                ("vendedor", vendedor_clave, "vendedor"),
            ):
                salt, clave_hash = crear_hash_clave(clave)
                conexion.execute("INSERT INTO public.usuarios (usuario, salt, clave_hash, rol) VALUES (%s, %s, %s, %s)", (usuario, salt, clave_hash, rol))
            return True

    def crear_usuario(self, usuario, clave, rol):
        salt, clave_hash = crear_hash_clave(clave)
        try:
            with self._transaccion_escritura() as conexion:
                conexion.execute("INSERT INTO public.usuarios (usuario, salt, clave_hash, rol) VALUES (%s, %s, %s, %s)", (usuario, salt, clave_hash, rol))
            return True
        except psycopg.errors.UniqueViolation:
            return False

    def cambiar_clave(self, usuario, clave_actual, clave_nueva):
        with self._transaccion_escritura() as conexion:
            registro = conexion.execute("SELECT salt, clave_hash, activo FROM public.usuarios WHERE usuario = %s FOR UPDATE", (usuario,)).fetchone()
            if not registro or not registro["activo"]:
                return False, "Usuario no disponible."
            if not verificar_clave(clave_actual, registro["salt"], registro["clave_hash"]):
                return False, "La contraseña actual es incorrecta."
            salt, clave_hash = crear_hash_clave(clave_nueva)
            conexion.execute("UPDATE public.usuarios SET salt = %s, clave_hash = %s WHERE usuario = %s", (salt, clave_hash, usuario))
        return True, "Contraseña actualizada correctamente."

    def registrar_auditoria(self, usuario, rol, accion, detalle, servidor, exito):
        with self._transaccion_escritura() as conexion:
            conexion.execute("INSERT INTO public.auditoria (usuario, rol, accion, detalle, servidor, exito) VALUES (%s, %s, %s, %s, %s, %s)", (usuario, rol, accion, detalle[:500], servidor, int(bool(exito))))

    def obtener_auditoria(self, limite=20):
        with self._conectar() as conexion:
            filas = conexion.execute("SELECT id, usuario, rol, accion, detalle, servidor, exito, creado_en FROM public.auditoria ORDER BY id DESC LIMIT %s", (limite,)).fetchall()
            for fila in filas:
                fila["creado_en"] = fila["creado_en"].isoformat()
            return filas

    def vender(self, id_producto, cantidad, request_id, usuario):
        return self._modificar_stock("vender", id_producto, cantidad, request_id, usuario)

    def agregar_stock(self, id_producto, cantidad, request_id, usuario):
        return self._modificar_stock("agregar_stock", id_producto, cantidad, request_id, usuario)

    def _modificar_stock(self, accion, id_producto, cantidad, request_id, usuario):
        if type(cantidad) is not int or not 1 <= cantidad <= 10000:
            return {"exito": False, "mensaje": "Cantidad inválida."}
        if not isinstance(request_id, str) or not request_id or len(request_id) > 80:
            return {"exito": False, "mensaje": "La operación requiere un request_id válido."}
        solicitud = {"accion": accion, "producto": id_producto, "cantidad": cantidad, "usuario": usuario}
        with self._transaccion_escritura() as conexion:
            self._bloquear_solicitud(conexion, "invax:operacion:" + request_id)
            previa = conexion.execute("SELECT usuario, respuesta_json FROM public.operaciones WHERE request_id = %s", (request_id,)).fetchone()
            if previa:
                guardada = json.loads(previa["respuesta_json"])
                if previa["usuario"] != usuario or guardada.get("solicitud") != solicitud:
                    return {"exito": False, "mensaje": "request_id ya utilizado con otros datos."}
                return {**guardada["respuesta"], "repetida": True}
            producto = conexion.execute("SELECT nombre, cantidad, version FROM public.productos WHERE id_producto = %s FOR UPDATE", (id_producto,)).fetchone()
            if producto is None:
                respuesta = {"exito": False, "mensaje": f"El producto {id_producto} no existe."}
            elif accion == "vender" and producto["cantidad"] < cantidad:
                respuesta = {"exito": False, "mensaje": "Stock insuficiente.", "stock_actual": producto["cantidad"]}
            else:
                anterior = producto["cantidad"]
                actual = anterior - cantidad if accion == "vender" else anterior + cantidad
                conexion.execute("UPDATE public.productos SET cantidad = %s, version = version + 1 WHERE id_producto = %s", (actual, id_producto))
                respuesta = {
                    "exito": True,
                    "mensaje": "Venta realizada correctamente." if accion == "vender" else "Stock actualizado correctamente.",
                    "producto": producto["nombre"], "stock_anterior": anterior,
                    "stock_actual": actual, "version": producto["version"] + 1,
                }
            documento = json.dumps({"solicitud": solicitud, "respuesta": respuesta}, ensure_ascii=False)
            conexion.execute("INSERT INTO public.operaciones (request_id, accion, usuario, respuesta_json) VALUES (%s, %s, %s, %s)", (request_id, accion, usuario, documento))
            return respuesta
