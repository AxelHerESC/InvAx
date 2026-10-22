import os
import unittest
from unittest.mock import patch

from configuracion import cargar_authkey_cliente, cargar_secretos_servidor, preparar_secretos
from seguridad import crear_token, verificar_token


class PruebasSecretosServidor(unittest.TestCase):
    def test_sesion_se_conserva_sin_archivos_locales(self):
        entorno = {
            "INVENTARIO_AUTHKEY": "conexion-interna-" * 4,
            "INVENTARIO_TOKEN_SECRET": "firma-de-sesiones-" * 4,
        }
        with patch.dict(os.environ, entorno, clear=True), patch("configuracion._guardar_privado", side_effect=AssertionError("No debe escribir secretos locales")):
            primero = preparar_secretos()
            token = crear_token("admin", "administrador", primero["token_secret"], 900)
            despues = cargar_secretos_servidor()
            self.assertEqual(verificar_token(token, despues["token_secret"])["u"], "admin")
            self.assertEqual(cargar_authkey_cliente(), primero["authkey"])

    def test_secretos_incompletos_no_generan_otros_por_accidente(self):
        with patch.dict(os.environ, {"INVENTARIO_AUTHKEY": "a" * 40}, clear=True):
            with self.assertRaises(ValueError):
                preparar_secretos()

    def test_secretos_cortos_se_rechazan(self):
        with patch.dict(os.environ, {"INVENTARIO_AUTHKEY": "corta", "INVENTARIO_TOKEN_SECRET": "corta"}, clear=True):
            with self.assertRaises(ValueError):
                cargar_secretos_servidor()

    def test_produccion_no_inicia_con_sqlite(self):
        from backend.iniciar_servidor import main
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                main()
