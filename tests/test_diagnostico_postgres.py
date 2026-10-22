import os
import unittest
from unittest.mock import MagicMock, patch

import psycopg

from inventario_postgres import AlmacenNoDisponible, InventarioPostgres, detalle_conexion_seguro, validar_database_url


class PruebasDiagnosticoPostgres(unittest.TestCase):
    def test_errores_sin_credenciales_ni_consultas(self):
        sensible = "postgresql://usuario:CONTRASENA_PRIVADA@servidor/db"
        casos = (
            (psycopg.OperationalError("password authentication failed " + sensible), "PG_AUTH"),
            (psycopg.OperationalError("Tenant or user not found " + sensible), "PG_POOLER"),
            (psycopg.OperationalError("connection timeout expired " + sensible), "PG_TIMEOUT"),
            (psycopg.OperationalError("could not translate host name " + sensible), "PG_DNS"),
            (psycopg.OperationalError("SSL connection error " + sensible), "PG_TLS"),
            (psycopg.errors.UndefinedTable(sensible), "PG_TABLA"),
            (psycopg.errors.UndefinedColumn(sensible), "PG_COLUMNA"),
            (psycopg.errors.InsufficientPrivilege(sensible), "PG_PERMISOS"),
            (psycopg.errors.LockNotAvailable(sensible), "PG_LOCK"),
            (psycopg.errors.QueryCanceled(sensible), "PG_QUERY_TIMEOUT"),
            (psycopg.errors.TooManyConnections(sensible), "PG_LIMITE"),
        )
        almacen = InventarioPostgres.__new__(InventarioPostgres)
        almacen.database_url = sensible
        for error, codigo in casos:
            with self.subTest(codigo=codigo), patch("inventario_postgres.psycopg.connect", side_effect=error):
                with self.assertRaises(AlmacenNoDisponible) as contexto:
                    with almacen._conectar():
                        self.fail("La conexión fallida no debe llegar al cuerpo.")
                mensaje = str(contexto.exception)
                self.assertTrue(mensaje.startswith(codigo + ":"), mensaje)
                self.assertNotIn("CONTRASENA_PRIVADA", mensaje)
                self.assertNotIn(sensible, mensaje)

    def test_scram_wrong_password_se_identifica_como_autenticacion(self):
        almacen = InventarioPostgres.__new__(InventarioPostgres)
        almacen.database_url = "postgresql://usuario:secreto@servidor/db"
        error = psycopg.OperationalError("error received from server in SCRAM exchange: Wrong password")
        with patch("inventario_postgres.psycopg.connect", side_effect=error):
            with self.assertRaisesRegex(AlmacenNoDisponible, "PG_AUTH.*Wrong password"):
                with almacen._conectar():
                    pass

    def test_detalle_oculta_password_original_codificado_y_uri(self):
        from urllib.parse import quote
        clave = "PRUEBA@#%/ valor"
        uri = "postgresql://usuario:" + quote(clave, safe="") + "@servidor/db"
        error = psycopg.OperationalError(f"Error de protocolo. {uri} password='{clave}' {clave} {quote(clave, safe='')}")
        detalle = detalle_conexion_seguro(error, uri, clave)
        self.assertIn("Error de protocolo", detalle)
        self.assertNotIn(clave, detalle)
        self.assertNotIn(quote(clave, safe=""), detalle)
        self.assertNotIn(uri, detalle)

    def test_detalle_oculta_otra_uri_e_identificador_password(self):
        error = psycopg.OperationalError("Fallo remoto postgresql://otro:CLAVE_AJENA@host/db password='OTRA_CLAVE'\nsegunda linea")
        detalle = detalle_conexion_seguro(error, "postgresql://usuario@servidor/db")
        self.assertNotIn("CLAVE_AJENA", detalle)
        self.assertNotIn("OTRA_CLAVE", detalle)
        self.assertNotIn("\n", detalle)

    def test_error_de_consulta_no_publica_el_texto_de_los_datos(self):
        class Conexion:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def execute(self, consulta):
                pass
        almacen = InventarioPostgres.__new__(InventarioPostgres)
        almacen.database_url = "postgresql://usuario:secreto@servidor/db"
        with patch("inventario_postgres.psycopg.connect", return_value=Conexion()):
            with self.assertRaises(AlmacenNoDisponible) as contexto:
                with almacen._conectar():
                    raise psycopg.errors.InsufficientPrivilege("CONTENIDO_PRIVADO_DE_LA_CONSULTA")
        self.assertNotIn("CONTENIDO_PRIVADO", str(contexto.exception))

    def test_validacion_local_sin_contactar_la_base(self):
        for uri in (
            "DATABASE_URL=postgresql://usuario:secreto@servidor/db",
            "'postgresql://usuario:secreto@servidor/db'",
            "postgresql://usuario:[YOUR-PASSWORD]@servidor/db",
            "postgresql://usuario@servidor/db",
            "postgresql://usuario:valor%NO@servidor/db",
        ):
            with self.subTest(uri=uri), patch("inventario_postgres.psycopg.connect") as conectar:
                with self.assertRaisesRegex(AlmacenNoDisponible, "PG_CONFIG"):
                    InventarioPostgres(uri)
                conectar.assert_not_called()

    def test_acepta_contrasena_codificada(self):
        validar_database_url("postgresql://postgres.proyecto:clave%40con%23signos@servidor:5432/postgres")

    def test_conflicto_unico_se_conserva_para_creacion_de_usuarios(self):
        almacen = InventarioPostgres.__new__(InventarioPostgres)
        almacen.database_url = "postgresql://usuario:secreto@servidor/db"
        with patch("inventario_postgres.psycopg.connect", return_value=MagicMock()):
            with self.assertRaises(psycopg.errors.UniqueViolation):
                with almacen._conectar():
                    raise psycopg.errors.UniqueViolation("duplicado")

    def test_password_separado_no_necesita_codificacion_uri(self):
        validar_database_url(
            "postgresql://postgres.proyecto@servidor:5432/postgres",
            "valor@con#porcentaje%y/espacio :",
        )

    def test_constructor_obtiene_password_de_variable_privada(self):
        uri = "postgresql://postgres.proyecto@servidor:5432/postgres"
        clave = "valor@con#porcentaje%y/espacio :"
        with patch.dict(os.environ, {"DATABASE_PASSWORD": clave}), patch.object(InventarioPostgres, "verificar_esquema"):
            almacen = InventarioPostgres(uri)
        self.assertEqual(almacen.database_password, clave)
        self.assertEqual(almacen.database_url, uri)

    def test_password_se_envia_tal_cual_como_parametro_separado(self):
        almacen = InventarioPostgres.__new__(InventarioPostgres)
        almacen.database_url = "postgresql://postgres.proyecto@servidor:5432/postgres"
        almacen.database_password = "valor@con#porcentaje%y/espacio :"
        with patch("inventario_postgres.psycopg.connect", side_effect=psycopg.OperationalError("password authentication failed")) as conectar:
            with self.assertRaisesRegex(AlmacenNoDisponible, "PG_AUTH"):
                with almacen._conectar():
                    pass
        self.assertEqual(conectar.call_args.args[0], almacen.database_url)
        self.assertEqual(conectar.call_args.kwargs["password"], almacen.database_password)
