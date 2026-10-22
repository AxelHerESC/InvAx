from multiprocessing import AuthenticationError
from multiprocessing.managers import BaseManager, RemoteError

from configuracion import SERVIDORES, cargar_authkey_cliente
from inventario_postgres import AlmacenNoDisponible


class GestorInventario(BaseManager):
    pass


GestorInventario.register("obtener_servicio_inventario")


class ClusterNoDisponible(Exception):
    pass


class ConexionCluster:
    def __init__(self, servidores=None, authkey=None):
        self.servidores = list(SERVIDORES if servidores is None else servidores)
        self.authkey = authkey

    def invocar(self, metodo, *argumentos):
        try:
            authkey = self.authkey or cargar_authkey_cliente()
        except FileNotFoundError as error:
            raise ClusterNoDisponible from error
        for _, host, puerto in self.servidores:
            try:
                gestor = GestorInventario(address=(host, puerto), authkey=authkey)
                gestor.connect()
                servicio = gestor.obtener_servicio_inventario()
                return getattr(servicio, metodo)(*argumentos)
            except (OSError, EOFError, AuthenticationError, RemoteError, AlmacenNoDisponible):
                continue
        raise ClusterNoDisponible

    def estado(self):
        authkey = self.authkey or cargar_authkey_cliente()
        nodos = []
        for servidor_id, host, puerto in self.servidores:
            disponible = False
            try:
                gestor = GestorInventario(address=(host, puerto), authkey=authkey)
                gestor.connect()
                disponible = bool(gestor.obtener_servicio_inventario().ping().get("exito"))
            except (OSError, EOFError, AuthenticationError, RemoteError):
                pass
            nodos.append({"servidor": servidor_id, "disponible": disponible})
        return nodos
