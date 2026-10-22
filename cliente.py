import getpass
import random
import uuid
from multiprocessing.managers import BaseManager

from configuracion import SERVIDORES, cargar_authkey_cliente


class GestorInventario(BaseManager):
    pass


GestorInventario.register("obtener_servicio_inventario")


class ClienteObjetosDistribuidos:
    def __init__(self, servidores=None):
        self.servidores = list(servidores or SERVIDORES)
        random.shuffle(self.servidores)
        self.authkey = cargar_authkey_cliente()
        self.gestor = None
        self.servicio = None
        self.servidor_actual = None
        self.token = None
        self.usuario = None
        self.rol = None
        self._credenciales = None

    def conectar(self, excluir=None):
        excluir = set(excluir or [])
        errores = []
        for servidor_id, host, puerto in self.servidores:
            clave = (servidor_id, host, puerto)
            if clave in excluir:
                continue
            try:
                gestor = GestorInventario(address=(host, puerto), authkey=self.authkey)
                gestor.connect()
                servicio = gestor.obtener_servicio_inventario()
                estado = servicio.ping()
                self.gestor = gestor
                self.servicio = servicio
                self.servidor_actual = clave
                print(f"Conectado al objeto remoto de {estado['servidor']} ({host}:{puerto}).")
                return
            except (OSError, EOFError, ConnectionError) as error:
                errores.append(f"{servidor_id}@{host}:{puerto} -> {error}")

        raise ConnectionError("No hay servidores disponibles. " + " | ".join(errores))

    def iniciar_sesion(self, usuario, clave):
        self._credenciales = (usuario, clave)
        respuesta = self._invocar("autenticar", usuario, clave, requiere_token=False)
        if respuesta.get("exito"):
            self.token = respuesta["token"]
            self.usuario = respuesta["usuario"]
            self.rol = respuesta["rol"]
        return respuesta

    def _reautenticar(self):
        if not self._credenciales:
            return False
        usuario, clave = self._credenciales
        respuesta = self.servicio.autenticar(usuario, clave)
        if not respuesta.get("exito"):
            return False
        self.token = respuesta["token"]
        self.usuario = respuesta["usuario"]
        self.rol = respuesta["rol"]
        return True

    def _invocar(self, metodo, *args, requiere_token=True):
        intentados = set()
        ultimo_error = None

        for _ in range(len(self.servidores)):
            if self.servicio is None:
                self.conectar(excluir=intentados)
                if requiere_token and self.token and not self._reautenticar():
                    raise ConnectionError("No fue posible restaurar la sesión.")

            servidor_usado = self.servidor_actual
            try:
                funcion = getattr(self.servicio, metodo)
                if requiere_token:
                    respuesta = funcion(self.token, *args)
                else:
                    respuesta = funcion(*args)

                if respuesta.get("requiere_login") and self._credenciales:
                    if self._reautenticar():
                        funcion = getattr(self.servicio, metodo)
                        respuesta = funcion(self.token, *args) if requiere_token else funcion(*args)
                return respuesta
            except (OSError, EOFError, ConnectionError, BrokenPipeError) as error:
                ultimo_error = error
                if servidor_usado is not None:
                    intentados.add(servidor_usado)
                print(f"Se perdió {servidor_usado}. Buscando otro objeto remoto...")
                self.gestor = None
                self.servicio = None
                self.servidor_actual = None

        raise ConnectionError(f"No fue posible completar la invocación remota: {ultimo_error}")

    def listar_inventario(self):
        return self._invocar("listar_inventario")

    def consultar_producto(self, id_producto):
        return self._invocar("consultar_producto", id_producto)

    def vender(self, id_producto, cantidad):
        request_id = str(uuid.uuid4())
        return self._invocar("vender", id_producto, cantidad, request_id)

    def agregar_stock(self, id_producto, cantidad):
        request_id = str(uuid.uuid4())
        return self._invocar("agregar_stock", id_producto, cantidad, request_id)

    def crear_usuario(self, usuario, clave, rol):
        return self._invocar("crear_usuario", usuario, clave, rol)

    def cambiar_clave(self, actual, nueva):
        return self._invocar("cambiar_clave", actual, nueva)

    def obtener_auditoria(self, limite=20):
        return self._invocar("obtener_auditoria", limite)


def mostrar_origen(respuesta):
    servidor = respuesta.get("servidor")
    if servidor:
        repetida = " | idempotente" if respuesta.get("repetida") else ""
        print(f"[Objeto remoto en {servidor}{repetida}]")


def mostrar_producto(producto):
    print(
        f"{producto['id']} | {producto['nombre']:<10} | "
        f"${producto['precio']:>9,.2f} | Stock: {producto['cantidad']} | "
        f"Versión: {producto.get('version', 0)}"
    )


def mostrar_inventario(productos):
    print("-" * 82)
    for producto in productos:
        mostrar_producto(producto)
    print("-" * 82)


def leer_cantidad():
    while True:
        try:
            cantidad = int(input("Cantidad: "))
        except ValueError:
            print("Debes ingresar un número entero.")
            continue
        if cantidad <= 0:
            print("La cantidad debe ser mayor que cero.")
            continue
        return cantidad


def consultar(cliente):
    id_producto = input("ID del producto: ").strip().upper()
    respuesta = cliente.consultar_producto(id_producto)
    mostrar_origen(respuesta)
    if respuesta["exito"]:
        mostrar_producto(respuesta["producto"])
    else:
        print(respuesta["mensaje"])


def listar(cliente):
    respuesta = cliente.listar_inventario()
    mostrar_origen(respuesta)
    if respuesta["exito"]:
        mostrar_inventario(respuesta["productos"])
    else:
        print(respuesta["mensaje"])


def cambiar_clave(cliente):
    actual = getpass.getpass("Contraseña actual: ")
    nueva = getpass.getpass("Nueva contraseña: ")
    confirmacion = getpass.getpass("Confirmar nueva contraseña: ")
    if nueva != confirmacion:
        print("Las contraseñas no coinciden.")
        return
    respuesta = cliente.cambiar_clave(actual, nueva)
    mostrar_origen(respuesta)
    print(respuesta["mensaje"])
    if respuesta["exito"]:
        cliente._credenciales = (cliente.usuario, nueva)


def menu_vendedor(cliente):
    while True:
        print("\n1. Mostrar inventario")
        print("2. Consultar producto")
        print("3. Realizar venta")
        print("4. Cambiar contraseña")
        print("0. Salir")
        opcion = input("Selecciona una opción: ").strip()

        if opcion == "1":
            listar(cliente)
        elif opcion == "2":
            consultar(cliente)
        elif opcion == "3":
            id_producto = input("ID del producto: ").strip().upper()
            respuesta = cliente.vender(id_producto, leer_cantidad())
            mostrar_origen(respuesta)
            print(respuesta["mensaje"])
            if respuesta["exito"]:
                print(f"Stock: {respuesta['stock_anterior']} -> {respuesta['stock_actual']}")
        elif opcion == "4":
            cambiar_clave(cliente)
        elif opcion == "0":
            return
        else:
            print("Opción inválida.")


def menu_administrador(cliente):
    while True:
        print("\n1. Mostrar inventario")
        print("2. Consultar producto")
        print("3. Agregar stock")
        print("4. Crear usuario")
        print("5. Ver auditoría")
        print("6. Cambiar contraseña")
        print("0. Salir")
        opcion = input("Selecciona una opción: ").strip()

        if opcion == "1":
            listar(cliente)
        elif opcion == "2":
            consultar(cliente)
        elif opcion == "3":
            id_producto = input("ID del producto: ").strip().upper()
            respuesta = cliente.agregar_stock(id_producto, leer_cantidad())
            mostrar_origen(respuesta)
            print(respuesta["mensaje"])
            if respuesta["exito"]:
                print(f"Stock: {respuesta['stock_anterior']} -> {respuesta['stock_actual']}")
        elif opcion == "4":
            usuario = input("Nuevo usuario: ").strip()
            clave = getpass.getpass("Contraseña: ")
            rol = input("Rol (vendedor/administrador): ").strip().lower()
            respuesta = cliente.crear_usuario(usuario, clave, rol)
            mostrar_origen(respuesta)
            print(respuesta["mensaje"])
        elif opcion == "5":
            respuesta = cliente.obtener_auditoria(20)
            mostrar_origen(respuesta)
            if respuesta["exito"]:
                for fila in respuesta["registros"]:
                    estado = "OK" if fila["exito"] else "FALLO"
                    print(
                        f"{fila['id']:>4} | {fila['creado_en']} | {estado:<5} | "
                        f"{fila['usuario']} ({fila['rol']}) | {fila['accion']} | "
                        f"{fila['servidor']} | {fila['detalle']}"
                    )
            else:
                print(respuesta["mensaje"])
        elif opcion == "6":
            cambiar_clave(cliente)
        elif opcion == "0":
            return
        else:
            print("Opción inválida.")


def main():
    print("=" * 76)
    print("CLIENTE - INVENTARIO CON OBJETOS DISTRIBUIDOS")
    print("=" * 76)

    cliente = ClienteObjetosDistribuidos()
    try:
        cliente.conectar()
        usuario = input("Usuario: ").strip()
        clave = getpass.getpass("Contraseña: ")
        respuesta = cliente.iniciar_sesion(usuario, clave)
        mostrar_origen(respuesta)
        print(respuesta["mensaje"])
        if not respuesta["exito"]:
            return

        print(f"Sesión: {cliente.usuario} ({cliente.rol})")
        if cliente.rol == "vendedor":
            menu_vendedor(cliente)
        else:
            menu_administrador(cliente)
    except (ConnectionError, FileNotFoundError) as error:
        print(error)


if __name__ == "__main__":
    main()
