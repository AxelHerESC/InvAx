"""Acceso a PostgreSQL delimitado por servicio y por roles SQL distintos."""
import json
import os
from decimal import Decimal, InvalidOperation
from uuid import UUID

import psycopg
from psycopg.conninfo import conninfo_to_dict

from inventario_postgres import InventarioPostgres, validar_database_url
from backend.microservices.common import ServiceError


def validate_product_id(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r"P[0-9]{3}", value):
        raise ServiceError(400, "El ID debe tener formato P001.")
    return value


def movement_data(product, quantity, request_id):
    validate_product_id(product)
    if type(quantity) is not int or not 1 <= quantity <= 10000:
        raise ServiceError(400, "La cantidad debe ser un entero entre 1 y 10000.")
    try:
        if not isinstance(request_id, str) or len(request_id) > 80:
            raise ValueError
        request_id = str(UUID(request_id))
    except ValueError:
        raise ServiceError(400, "request_id debe ser un UUID válido.") from None
    return product, quantity, request_id


def metadata(data, create=False):
    allowed = {"id", "nombre", "precio", "cantidad"} if create else {"nombre", "precio", "version"}
    if not isinstance(data, dict) or not data or set(data)-allowed:
        raise ServiceError(422, "Campos del producto inválidos.")
    if create:
        validate_product_id(data.get("id"))
    elif type(data.get("version")) is not int or data["version"] < 0:
        raise ServiceError(422, "Incluye la versión consultada para evitar sobrescribir cambios.")
    if create or "nombre" in data:
        if not isinstance(data.get("nombre"), str) or not 1 <= len(data["nombre"].strip()) <= 256 or any(0xD800 <= ord(c) <= 0xDFFF for c in data["nombre"]):
            raise ServiceError(422, "Escribe un nombre de hasta 256 caracteres.")
    if create or "precio" in data:
        try:
            if isinstance(data.get("precio"), bool):
                raise InvalidOperation
            price = Decimal(str(data.get("precio")))
            if not price.is_finite() or not 0 <= price <= Decimal("9999999999.99") or price != price.quantize(Decimal("0.01")):
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            raise ServiceError(422, "Precio inválido; utiliza hasta dos decimales.") from None
    if create and (type(data.get("cantidad", 0)) is not int or not 0 <= data.get("cantidad", 0) <= 10000):
        raise ServiceError(422, "Existencias iniciales inválidas.")
    return {**data, **({"nombre": data["nombre"].strip()} if "nombre" in data else {})}


class RestrictedStore(InventarioPostgres):
    role = None

    def __init__(self, url):
        self.database_password = os.environ.get("DATABASE_PASSWORD")
        validar_database_url(url, self.database_password)
        self.database_url = url
        # El pooler admite usuario rol.referencia. Nunca usar postgres en P08.
        if conninfo_to_dict(url).get("user", "").split(".")[0] != self.role:
            raise RuntimeError("Configura la conexión con el rol SQL específico del microservicio.")
        self.verificar_esquema()


class AuthStore(RestrictedStore):
    role = "invax_auth"

    def verificar_esquema(self):
        with self._conectar() as c:
            c.execute("SELECT usuario, salt, clave_hash, rol, activo FROM public.usuarios LIMIT 0")
            c.execute("SELECT id, usuario, rol, accion, detalle, servidor, exito, creado_en FROM public.auditoria LIMIT 0")


class ProductStore(RestrictedStore):
    role = "invax_productos"

    def verificar_esquema(self):
        with self._conectar() as c:
            c.execute("SELECT id_producto, nombre, precio, cantidad, version FROM public.productos LIMIT 0")
            c.execute("SELECT request_id, accion, usuario, respuesta_json, creado_en FROM public.operaciones LIMIT 0")

    @staticmethod
    def audit(c, actor, action, detail, success):
        c.execute("INSERT INTO public.auditoria (usuario, rol, accion, detalle, servidor, exito) VALUES (%s,%s,%s,%s,%s,%s)",
                  (actor["usuario"], actor["rol"], action, detail[:500], "productos", int(success)))

    def create_product(self, data, actor):
        data = metadata(data, True)
        try:
            with self._conectar() as c:
                c.execute("INSERT INTO public.productos (id_producto,nombre,precio,cantidad,version) VALUES (%s,%s,%s,%s,0)",
                          (data["id"], data["nombre"], Decimal(str(data["precio"])), data.get("cantidad", 0)))
                self.audit(c, actor, "crear_producto", "producto="+data["id"], True)
            return {"exito": True, "mensaje": "Producto creado correctamente."}, 201
        except psycopg.errors.UniqueViolation:
            return {"exito": False, "mensaje": "El ID de producto ya existe."}, 409

    def edit_product(self, product, data, actor):
        validate_product_id(product)
        data = metadata(data)
        with self._conectar() as c:
            row = c.execute("SELECT id_producto,nombre,precio,cantidad,version FROM public.productos WHERE id_producto=%s FOR UPDATE", (product,)).fetchone()
            if row is None:
                raise ServiceError(404, "Producto no encontrado.")
            if row["version"] != data["version"]:
                raise ServiceError(409, "El producto cambió. Actualiza el catálogo antes de editarlo.")
            c.execute("UPDATE public.productos SET nombre=%s, precio=%s, version=version+1 WHERE id_producto=%s",
                      (data.get("nombre", row["nombre"]), Decimal(str(data.get("precio", row["precio"]))), product))
            self.audit(c, actor, "editar_producto", "producto="+product, True)
        return {"exito": True, "mensaje": "Producto actualizado correctamente."}

    def delete_product(self, product, version, actor):
        validate_product_id(product)
        if type(version) is not int or version < 0:
            raise ServiceError(422, "Incluye la versión del producto.")
        with self._conectar() as c:
            row = c.execute("SELECT cantidad,version FROM public.productos WHERE id_producto=%s FOR UPDATE", (product,)).fetchone()
            if row is None:
                raise ServiceError(404, "Producto no encontrado.")
            # Todos los movimientos toman este mismo bloqueo antes de insertar su registro.
            history = c.execute("SELECT 1 FROM public.operaciones WHERE respuesta_json::jsonb -> 'solicitud' ->> 'producto'=%s LIMIT 1", (product,)).fetchone()
            if row["version"] != version or row["cantidad"] != 0 or history:
                raise ServiceError(409, "Solo se eliminan productos sin stock ni historial y con versión vigente.")
            c.execute("DELETE FROM public.productos WHERE id_producto=%s", (product,))
            self.audit(c, actor, "eliminar_producto", "producto="+product, True)
        return {"exito": True, "mensaje": "Producto eliminado correctamente."}

    def move(self, action, product, quantity, request_id, actor):
        product, quantity, request_id = movement_data(product, quantity, request_id)
        if action not in ("vender", "agregar_stock"):
            raise ServiceError(400, "Movimiento inválido.")
        expected = "vendedor" if action == "vender" else "administrador"
        if actor["rol"] != expected:
            raise ServiceError(403, "Rol no autorizado para el movimiento.")
        payload = {"accion": action, "producto": product, "cantidad": quantity, "usuario": actor["usuario"]}
        with self._conectar() as c:
            self._bloquear_solicitud(c, "invax:operacion:"+request_id)
            old = c.execute("SELECT usuario,respuesta_json FROM public.operaciones WHERE request_id=%s", (request_id,)).fetchone()
            if old:
                stored = json.loads(old["respuesta_json"])
                if old["usuario"] != actor["usuario"] or stored.get("solicitud") != payload:
                    raise ServiceError(409, "request_id ya utilizado con otros datos.")
                answer = {**stored["respuesta"], "repetida": True}
                return answer, 200 if answer["exito"] else 409
            row = c.execute("SELECT nombre,cantidad,version FROM public.productos WHERE id_producto=%s FOR UPDATE", (product,)).fetchone()
            if row is None:
                answer = {"exito": False, "mensaje": "Producto no encontrado."}
            elif action == "vender" and row["cantidad"] < quantity:
                answer = {"exito": False, "mensaje": "Stock insuficiente.", "stock_actual": row["cantidad"]}
            elif action == "agregar_stock" and row["cantidad"] > 2147483647-quantity:
                answer = {"exito": False, "mensaje": "Se alcanzó el límite de existencias."}
            else:
                current = row["cantidad"]+(-quantity if action == "vender" else quantity)
                c.execute("UPDATE public.productos SET cantidad=%s,version=version+1 WHERE id_producto=%s", (current, product))
                answer = {"exito": True, "mensaje": "Venta realizada correctamente." if action == "vender" else "Stock actualizado correctamente.",
                          "producto": row["nombre"], "stock_anterior": row["cantidad"], "stock_actual": current, "version": row["version"]+1}
            c.execute("INSERT INTO public.operaciones (request_id,accion,usuario,respuesta_json) VALUES (%s,%s,%s,%s)",
                      (request_id, action, actor["usuario"], json.dumps({"solicitud": payload, "respuesta": answer}, ensure_ascii=False)))
            self.audit(c, actor, action, f"producto={product}; cantidad={quantity}; request_id={request_id}", answer["exito"])
            return answer, 200 if answer["exito"] else 409

    def history(self, action, actor, limit):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError(400, "El límite debe estar entre 1 y 100.")
        with self._conectar() as c:
            rows = c.execute("SELECT request_id,usuario,respuesta_json,creado_en FROM public.operaciones WHERE accion=%s AND (%s OR usuario=%s) ORDER BY creado_en DESC,request_id DESC LIMIT %s",
                             (action, actor["rol"] == "administrador", actor["usuario"], limit)).fetchall()
        return [{"request_id": r["request_id"], "usuario": r["usuario"], "creado_en": r["creado_en"].isoformat(), **json.loads(r["respuesta_json"])} for r in rows]
