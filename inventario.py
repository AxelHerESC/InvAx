import json
import sqlite3
from contextlib import contextmanager

from modelos import Producto
from seguridad import crear_hash_clave, verificar_clave


PRODUCTOS_INICIALES = [
    Producto("P001", "Laptop", 15000, 10),
    Producto("P002", "Mouse", 350, 25),
    Producto("P003", "Teclado", 700, 15),
    Producto("P004", "Monitor", 4500, 8),
]


class InventarioDistribuido:
    """Persistencia compartida por varios procesos servidor."""

    def __init__(self, ruta_bd="inventario.db"):
        self.ruta_bd = str(ruta_bd)
        self._inicializar_base()

    def _conectar(self):
        conexion = sqlite3.connect(
            self.ruta_bd,
            timeout=8.0,
            isolation_level=None,
        )
        conexion.row_factory = sqlite3.Row
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.execute("PRAGMA busy_timeout = 8000")
        return conexion

    def _inicializar_base(self):
        with self._conectar() as conexion:
            conexion.execute("PRAGMA journal_mode = WAL")
            conexion.execute("PRAGMA synchronous = NORMAL")

            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS productos (
                    id_producto TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    precio REAL NOT NULL CHECK(precio >= 0),
                    cantidad INTEGER NOT NULL CHECK(cantidad >= 0),
                    version INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS operaciones (
                    request_id TEXT PRIMARY KEY,
                    accion TEXT NOT NULL,
                    usuario TEXT NOT NULL,
                    respuesta_json TEXT NOT NULL,
                    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    clave_hash TEXT NOT NULL,
                    rol TEXT NOT NULL CHECK(rol IN ('vendedor', 'administrador')),
                    activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0, 1)),
                    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    detalle TEXT NOT NULL,
                    servidor TEXT NOT NULL,
                    exito INTEGER NOT NULL CHECK(exito IN (0, 1)),
                    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conexion.executemany(
                """
                INSERT OR IGNORE INTO productos
                    (id_producto, nombre, precio, cantidad, version)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        producto.id_producto,
                        producto.nombre,
                        producto.precio,
                        producto.cantidad,
                        producto.version,
                    )
                    for producto in PRODUCTOS_INICIALES
                ],
            )

    def asegurar_usuarios_iniciales(self, admin_clave, vendedor_clave):
        with self._transaccion_escritura() as conexion:
            cantidad = conexion.execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()[
                "total"
            ]
            if cantidad:
                return False

            salt_admin, hash_admin = crear_hash_clave(admin_clave)
            salt_vendedor, hash_vendedor = crear_hash_clave(vendedor_clave)
            conexion.executemany(
                """
                INSERT INTO usuarios (usuario, salt, clave_hash, rol)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("admin", salt_admin, hash_admin, "administrador"),
                    ("vendedor", salt_vendedor, hash_vendedor, "vendedor"),
                ],
            )
            return True

    @contextmanager
    def _transaccion_escritura(self):
        conexion = self._conectar()
        try:
            conexion.execute("BEGIN IMMEDIATE")
            yield conexion
            conexion.execute("COMMIT")
        except Exception:
            try:
                conexion.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conexion.close()

    @staticmethod
    def _fila_a_producto(fila):
        if fila is None:
            return None
        return Producto(
            fila["id_producto"],
            fila["nombre"],
            fila["precio"],
            fila["cantidad"],
            fila["version"],
        ).a_diccionario()

    def consultar_producto(self, id_producto):
        with self._conectar() as conexion:
            fila = conexion.execute(
                """
                SELECT id_producto, nombre, precio, cantidad, version
                FROM productos
                WHERE id_producto = ?
                """,
                (id_producto,),
            ).fetchone()
            return self._fila_a_producto(fila)

    def obtener_inventario(self):
        with self._conectar() as conexion:
            filas = conexion.execute(
                """
                SELECT id_producto, nombre, precio, cantidad, version
                FROM productos
                ORDER BY id_producto
                """
            ).fetchall()
            return [self._fila_a_producto(fila) for fila in filas]

    def obtener_usuario(self, usuario):
        with self._conectar() as conexion:
            fila = conexion.execute(
                """
                SELECT usuario, salt, clave_hash, rol, activo
                FROM usuarios WHERE usuario = ?
                """,
                (usuario,),
            ).fetchone()
            return dict(fila) if fila else None

    def autenticar_usuario(self, usuario, clave):
        registro = self.obtener_usuario(usuario)
        if not registro or not registro["activo"]:
            return None
        if not verificar_clave(clave, registro["salt"], registro["clave_hash"]):
            return None
        return {"usuario": registro["usuario"], "rol": registro["rol"]}

    def usuario_activo_con_rol(self, usuario, rol):
        registro = self.obtener_usuario(usuario)
        return bool(registro and registro["activo"] and registro["rol"] == rol)

    def crear_usuario(self, usuario, clave, rol):
        salt, clave_hash = crear_hash_clave(clave)
        try:
            with self._transaccion_escritura() as conexion:
                conexion.execute(
                    """
                    INSERT INTO usuarios (usuario, salt, clave_hash, rol)
                    VALUES (?, ?, ?, ?)
                    """,
                    (usuario, salt, clave_hash, rol),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def cambiar_clave(self, usuario, clave_actual, clave_nueva):
        registro = self.obtener_usuario(usuario)
        if not registro or not registro["activo"]:
            return False, "Usuario no disponible."
        if not verificar_clave(clave_actual, registro["salt"], registro["clave_hash"]):
            return False, "La contraseña actual es incorrecta."

        salt, clave_hash = crear_hash_clave(clave_nueva)
        with self._transaccion_escritura() as conexion:
            conexion.execute(
                "UPDATE usuarios SET salt = ?, clave_hash = ? WHERE usuario = ?",
                (salt, clave_hash, usuario),
            )
        return True, "Contraseña actualizada correctamente."

    def registrar_auditoria(self, usuario, rol, accion, detalle, servidor, exito):
        with self._transaccion_escritura() as conexion:
            conexion.execute(
                """
                INSERT INTO auditoria (usuario, rol, accion, detalle, servidor, exito)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (usuario, rol, accion, detalle[:500], servidor, int(bool(exito))),
            )

    def obtener_auditoria(self, limite=20):
        with self._conectar() as conexion:
            filas = conexion.execute(
                """
                SELECT id, usuario, rol, accion, detalle, servidor, exito, creado_en
                FROM auditoria
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,),
            ).fetchall()
            return [dict(fila) for fila in filas]

    def _buscar_operacion(self, conexion, request_id):
        fila = conexion.execute(
            "SELECT respuesta_json FROM operaciones WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if fila is None:
            return None
        respuesta = json.loads(fila["respuesta_json"])
        respuesta["repetida"] = True
        return respuesta

    @staticmethod
    def _guardar_operacion(conexion, request_id, accion, usuario, respuesta):
        conexion.execute(
            """
            INSERT INTO operaciones (request_id, accion, usuario, respuesta_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                request_id,
                accion,
                usuario,
                json.dumps(respuesta, ensure_ascii=False),
            ),
        )

    def vender(self, id_producto, cantidad, request_id, usuario):
        if cantidad <= 0:
            return {"exito": False, "mensaje": "La cantidad debe ser mayor que cero."}
        if not request_id:
            return {"exito": False, "mensaje": "La operación requiere request_id."}

        with self._transaccion_escritura() as conexion:
            repetida = self._buscar_operacion(conexion, request_id)
            if repetida is not None:
                return repetida

            producto = conexion.execute(
                """
                SELECT id_producto, nombre, cantidad, version
                FROM productos WHERE id_producto = ?
                """,
                (id_producto,),
            ).fetchone()

            if producto is None:
                respuesta = {"exito": False, "mensaje": f"El producto {id_producto} no existe."}
            elif producto["cantidad"] < cantidad:
                respuesta = {
                    "exito": False,
                    "mensaje": "Stock insuficiente.",
                    "stock_actual": producto["cantidad"],
                }
            else:
                stock_anterior = producto["cantidad"]
                resultado = conexion.execute(
                    """
                    UPDATE productos
                    SET cantidad = cantidad - ?, version = version + 1
                    WHERE id_producto = ? AND cantidad >= ?
                    """,
                    (cantidad, id_producto, cantidad),
                )
                if resultado.rowcount != 1:
                    actual = conexion.execute(
                        "SELECT cantidad FROM productos WHERE id_producto = ?",
                        (id_producto,),
                    ).fetchone()
                    respuesta = {
                        "exito": False,
                        "mensaje": "La operación perdió una carrera de actualización.",
                        "stock_actual": actual["cantidad"] if actual else None,
                    }
                else:
                    respuesta = {
                        "exito": True,
                        "mensaje": "Venta realizada correctamente.",
                        "producto": producto["nombre"],
                        "stock_anterior": stock_anterior,
                        "stock_actual": stock_anterior - cantidad,
                        "version": producto["version"] + 1,
                    }

            self._guardar_operacion(conexion, request_id, "vender", usuario, respuesta)
            return respuesta

    def agregar_stock(self, id_producto, cantidad, request_id, usuario):
        if cantidad <= 0:
            return {"exito": False, "mensaje": "La cantidad debe ser mayor que cero."}
        if not request_id:
            return {"exito": False, "mensaje": "La operación requiere request_id."}

        with self._transaccion_escritura() as conexion:
            repetida = self._buscar_operacion(conexion, request_id)
            if repetida is not None:
                return repetida

            producto = conexion.execute(
                """
                SELECT id_producto, nombre, cantidad, version
                FROM productos WHERE id_producto = ?
                """,
                (id_producto,),
            ).fetchone()

            if producto is None:
                respuesta = {"exito": False, "mensaje": f"El producto {id_producto} no existe."}
            else:
                stock_anterior = producto["cantidad"]
                conexion.execute(
                    """
                    UPDATE productos
                    SET cantidad = cantidad + ?, version = version + 1
                    WHERE id_producto = ?
                    """,
                    (cantidad, id_producto),
                )
                respuesta = {
                    "exito": True,
                    "mensaje": "Stock actualizado correctamente.",
                    "producto": producto["nombre"],
                    "stock_anterior": stock_anterior,
                    "stock_actual": stock_anterior + cantidad,
                    "version": producto["version"] + 1,
                }

            self._guardar_operacion(
                conexion, request_id, "agregar_stock", usuario, respuesta
            )
            return respuesta
