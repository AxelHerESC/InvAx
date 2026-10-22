import multiprocessing
import secrets
import tempfile
import unittest
from pathlib import Path

from backend.app import create_app


def ejecutar_nodo(ruta_bd, authkey, secreto, canal):
    from multiprocessing.managers import BaseManager
    from inventario import InventarioDistribuido
    from servicio_remoto import ServicioInventarioRemoto
    inventario = InventarioDistribuido(ruta_bd)
    inventario.asegurar_usuarios_iniciales("AdminPrueba2026!", "VentaPrueba2026!")
    servicio = ServicioInventarioRemoto(inventario, "PRUEBA", secreto)
    class Gestor(BaseManager):
        pass
    Gestor.register("obtener_servicio_inventario", callable=lambda: servicio)
    servidor = Gestor(address=("127.0.0.1", 0), authkey=authkey).get_server()
    canal.send(servidor.address[1])
    canal.close()
    servidor.serve_forever()


class PruebasBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal = tempfile.TemporaryDirectory()
        cls.authkey = secrets.token_bytes(32)
        receptor, emisor = multiprocessing.Pipe(duplex=False)
        cls.proceso = multiprocessing.Process(target=ejecutar_nodo, args=(
            str(Path(cls.temporal.name) / "prueba.db"), cls.authkey,
            secrets.token_bytes(32), emisor), daemon=True)
        cls.proceso.start()
        emisor.close()
        if not receptor.poll(15):
            cls.proceso.terminate()
            cls.proceso.join()
            cls.temporal.cleanup()
            raise RuntimeError("El nodo de prueba no inició.")
        cls.puerto = receptor.recv()
        receptor.close()
        cls.app = create_app([("PRUEBA", "127.0.0.1", cls.puerto)], cls.authkey)
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.proceso.terminate()
        cls.proceso.join(timeout=5)
        cls.temporal.cleanup()

    def setUp(self):
        self.cliente = self.app.test_client()

    def test_salud_sin_cluster(self):
        cliente = create_app(servidores=[]).test_client()
        self.assertEqual(cliente.get("/api/salud").status_code, 200)

    def test_listo_comprueba_objeto_y_persistencia(self):
        respuesta = self.cliente.get("/api/listo")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json["servidor"], "PRUEBA")

    def test_listo_sin_cluster(self):
        cliente = create_app(servidores=[], authkey=self.authkey).test_client()
        self.assertEqual(cliente.get("/api/listo").status_code, 503)

    def test_login_y_productos_reales(self):
        respuesta = self.cliente.post("/api/login", json={"usuario": "admin", "clave": "AdminPrueba2026!"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json["rol"], "administrador")
        productos = self.cliente.get("/api/productos", headers={"Authorization": "Bearer " + respuesta.json["token"]})
        self.assertEqual(productos.status_code, 200)
        self.assertEqual(len(productos.json["productos"]), 4)
        self.assertEqual(productos.json["servidor"], "PRUEBA")
        self.assertEqual(productos.headers["Cache-Control"], "no-store")

    def test_credenciales_incorrectas(self):
        r = self.cliente.post("/api/login", json={"usuario": "admin", "clave": "incorrecta"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("token", r.json)

    def test_login_invalido(self):
        for datos in ([], {}, {"usuario": [], "clave": 123}):
            with self.subTest(datos=datos):
                self.assertEqual(self.cliente.post("/api/login", json=datos).status_code, 400)

    def test_token_ausente_o_alterado(self):
        for cabecera in ("", "Bearer inventado", "Bearer á.firma"):
            with self.subTest(cabecera=cabecera):
                self.assertEqual(self.cliente.get("/api/productos", headers={"Authorization": cabecera}).status_code, 401)

    def test_cluster_no_disponible(self):
        cliente = create_app(servidores=[], authkey=self.authkey).test_client()
        r = cliente.post("/api/login", json={"usuario": "admin", "clave": "AdminPrueba2026!"})
        self.assertEqual(r.status_code, 503)

    def test_rutas_y_metodos_invalidos(self):
        for metodo, ruta, esperado in (("get", "/api/no-existe", 404), ("post", "/api/productos", 405)):
            r = getattr(self.cliente, metodo)(ruta)
            self.assertEqual(r.status_code, esperado)
            self.assertFalse(r.json["exito"])

    def test_respaldo_ante_nodo_caido(self):
        cliente = create_app([("CAIDO", "127.0.0.1", 0), ("PRUEBA", "127.0.0.1", self.puerto)], self.authkey).test_client()
        r = cliente.post("/api/login", json={"usuario": "vendedor", "clave": "VentaPrueba2026!"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["servidor"], "PRUEBA")


if __name__ == "__main__":
    unittest.main()
