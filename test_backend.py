import multiprocessing
import secrets
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
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

    def acceso(self, usuario="admin", clave="AdminPrueba2026!"):
        r = self.cliente.post("/api/login", json={"usuario": usuario, "clave": clave})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": "Bearer " + r.json["token"]}

    def test_pagina_principal_y_assets(self):
        with self.cliente.get("/") as r:
            self.assertEqual(r.status_code, 200)
            self.assertIn(b"InvAx", r.data)
            self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        for asset in ("app.js", "styles.css", "favicon.svg"):
            with self.cliente.get("/assets/" + asset) as r:
                self.assertEqual(r.status_code, 200)

    def test_sesion_y_estado_de_servidores(self):
        h = self.acceso()
        r = self.cliente.get("/api/sesion", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["rol"], "administrador")
        r = self.cliente.get("/api/servidores", headers=h)
        self.assertEqual(r.json["servidores"], [{"servidor": "PRUEBA", "disponible": True}])

    def test_reposicion_con_permisos_y_reintento(self):
        admin = self.acceso()
        vendedor = self.acceso("vendedor", "VentaPrueba2026!")
        antes = self.cliente.get("/api/productos/P002", headers=admin).json["producto"]["cantidad"]
        datos = {"id_producto": "P002", "cantidad": 7, "request_id": str(uuid.uuid4())}
        rechazo = self.cliente.post("/api/reposiciones", headers=vendedor, json=datos)
        self.assertEqual(rechazo.status_code, 403)
        r = self.cliente.post("/api/reposiciones", headers=admin, json=datos)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["stock_actual"], antes + 7)
        r = self.cliente.post("/api/reposiciones", headers=admin, json=datos)
        self.assertTrue(r.json["repetida"])
        self.assertEqual(self.cliente.get("/api/productos/P002", headers=admin).json["producto"]["cantidad"], antes + 7)

    def test_venta_idempotente_y_stock_insuficiente(self):
        h = self.acceso("vendedor", "VentaPrueba2026!")
        antes = self.cliente.get("/api/productos/P003", headers=h).json["producto"]["cantidad"]
        datos = {"id_producto": "P003", "cantidad": 1, "request_id": str(uuid.uuid4())}
        for _ in range(2):
            r = self.cliente.post("/api/ventas", headers=h, json=datos)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json["stock_actual"], antes - 1)
        self.assertTrue(r.json["repetida"])
        datos.update(cantidad=10000, request_id=str(uuid.uuid4()))
        self.assertEqual(self.cliente.post("/api/ventas", headers=h, json=datos).status_code, 409)
        self.assertEqual(self.cliente.get("/api/productos/P003", headers=h).json["producto"]["cantidad"], antes - 1)
        self.assertEqual(self.cliente.post("/api/ventas", headers=self.acceso(), json=datos).status_code, 403)

    def test_validacion_de_movimientos(self):
        h = self.acceso("vendedor", "VentaPrueba2026!")
        for cantidad in (True, False, 1.5, "2", 0, -1, 10001, None):
            with self.subTest(cantidad=cantidad):
                datos = {"id_producto": "P001", "cantidad": cantidad, "request_id": str(uuid.uuid4())}
                self.assertEqual(self.cliente.post("/api/ventas", headers=h, json=datos).status_code, 400)
        self.assertEqual(self.cliente.post("/api/ventas", headers=h, json={"id_producto": "P001", "cantidad": 1}).status_code, 400)

    def test_creacion_usuario_y_cambio_clave(self):
        admin = self.acceso()
        usuario = "ventas_" + uuid.uuid4().hex[:12]
        datos = {"usuario": usuario, "clave": "CuentaPrueba2026!", "rol": "vendedor"}
        r = self.cliente.post("/api/usuarios", headers=admin, json=datos)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.cliente.post("/api/usuarios", headers=admin, json=datos).status_code, 409)
        h = self.acceso(usuario, datos["clave"])
        self.assertEqual(self.cliente.get("/api/auditoria", headers=h).status_code, 403)
        self.assertEqual(self.cliente.post("/api/usuarios", headers=h, json=datos).status_code, 403)
        self.assertEqual(self.cliente.put("/api/clave", headers=h, json={"clave_actual": "incorrecta", "clave_nueva": "NuevaPrueba2026!"}).status_code, 400)
        self.assertEqual(self.cliente.put("/api/clave", headers=h, json={"clave_actual": datos["clave"], "clave_nueva": "NuevaPrueba2026!"}).status_code, 200)
        self.assertEqual(self.cliente.post("/api/login", json={"usuario": usuario, "clave": datos["clave"]}).status_code, 401)
        self.acceso(usuario, "NuevaPrueba2026!")
        auditoria = self.cliente.get("/api/auditoria?limite=100", headers=admin)
        self.assertEqual(auditoria.status_code, 200)
        self.assertTrue(any(r["accion"] == "crear_usuario" and usuario in r["detalle"] for r in auditoria.json["registros"]))

    def test_ventas_concurrentes_no_exceden_existencias_sqlite(self):
        h = self.acceso("vendedor", "VentaPrueba2026!")
        antes = self.cliente.get("/api/productos/P004", headers=h).json["producto"]["cantidad"]
        def vender(_):
            with self.app.test_client() as cliente:
                return cliente.post("/api/ventas", headers=h, json={"id_producto": "P004", "cantidad": 3, "request_id": str(uuid.uuid4())}).status_code
        with ThreadPoolExecutor(max_workers=6) as ejecutor:
            resultados = list(ejecutor.map(vender, range(6)))
        self.assertTrue(all(r in (200, 409) for r in resultados))
        self.assertEqual(resultados.count(200), min(6, antes // 3))
        despues = self.cliente.get("/api/productos/P004", headers=h).json["producto"]["cantidad"]
        self.assertEqual(despues, antes - resultados.count(200) * 3)
        self.assertGreaterEqual(despues, 0)

    def test_rutas_privadas_exigen_sesion(self):
        for metodo, ruta in (("get", "/api/sesion"), ("get", "/api/servidores"), ("get", "/api/auditoria"), ("post", "/api/ventas"), ("post", "/api/reposiciones"), ("post", "/api/usuarios"), ("put", "/api/clave")):
            with self.subTest(ruta=ruta):
                self.assertEqual(getattr(self.cliente, metodo)(ruta).status_code, 401)

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
