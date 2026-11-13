"""Fábricas de aplicaciones separadas y catálogo explícito de operaciones HTTP RPC."""
from backend.microservices.common import authorize, internal_app, ServiceError
from backend.microservices.stores import movement_data, validate_product_id
from servicio_remoto import ServicioInventarioRemoto


def create_auth(store, secret, cluster_token):
    service = ServicioInventarioRemoto(store, "auth", secret)
    # La interfaz heredada se reutiliza únicamente para identidad, cuentas y auditoría.
    methods = {name: getattr(service, name) for name in
               ("autenticar", "obtener_sesion", "crear_usuario", "cambiar_clave", "obtener_auditoria")}
    def login(usuario, clave):
        if not isinstance(usuario, str) or not isinstance(clave, str) or len(usuario)>32 or len(clave)>256:
            raise ServiceError(400, "Credenciales inválidas.")
        result = service.autenticar(usuario, clave)
        return result, 200 if result["exito"] else 401

    def create_user(token, usuario, clave, rol):
        result = service.crear_usuario(token, usuario, clave, rol)
        if result.get("requiere_login") or result.get("codigo"):
            return result
        return result, 201 if result["exito"] else 409 if result["mensaje"] == "El usuario ya existe." else 400

    def ready():
        store.obtener_usuario("__health__")
        return {"exito": True, "servicio": "auth"}

    methods["autenticar"] = login
    methods["crear_usuario"] = create_user
    methods["ping"] = ready
    return internal_app("auth", cluster_token, methods)


def create_products(store, client, cluster_token):
    def catalog(token):
        authorize(client, token)
        return {"exito": True, "mensaje": "Inventario consultado.", "servidor": "productos", "productos": store.obtener_inventario()}

    def product(token, id_product):
        authorize(client, token)
        validate_product_id(id_product)
        row = store.consultar_producto(id_product)
        if row is None:
            raise ServiceError(404, "Producto no encontrado.")
        return {"exito": True, "producto": row, "servidor": "productos"}

    def stock(token, action, id_product, quantity, request_id):
        actor = authorize(client, token)
        return store.move(action, id_product, quantity, request_id, actor)

    def create(token, data):
        return store.create_product(data, authorize(client, token, ("administrador",)))

    def edit(token, id_product, data):
        return store.edit_product(id_product, data, authorize(client, token, ("administrador",)))

    def delete(token, id_product, version):
        return store.delete_product(id_product, version, authorize(client, token, ("administrador",)))

    def history(token, action, limit):
        actor = authorize(client, token)
        if action not in ("vender", "agregar_stock"):
            raise ServiceError(400, "Tipo de historial inválido.")
        if action == "agregar_stock" and actor["rol"] != "administrador":
            raise ServiceError(403, "Solo administradores pueden consultar reposiciones.")
        return {"exito": True, "operaciones": store.history(action, actor, limit)}

    def ready():
        store.obtener_inventario()
        return {"exito": True, "servidor": "productos", "mensaje": "Persistencia disponible."}

    methods = {"listar_inventario": catalog, "consultar_producto": product, "stock": stock,
               "crear_producto": create, "editar_producto": edit, "eliminar_producto": delete,
               "historial": history, "comprobar_disponibilidad": ready, "ping": ready}
    return internal_app("productos", cluster_token, methods)


def create_movements(name, client, cluster_token):
    is_sale = name == "ventas"
    action = "vender" if is_sale else "agregar_stock"
    role = "vendedor" if is_sale else "administrador"

    def register(token, product, quantity, request_id):
        authorize(client, token, (role,))
        product, quantity, request_id = movement_data(product, quantity, request_id)
        # No hay SELECT + UPDATE entre servicios: un único comando transaccional.
        body, status = client.call("productos", "stock", [token, action, product, quantity, request_id])
        return {**body, "servidor": name}, status

    def history(token, limit):
        authorize(client, token, None if is_sale else ("administrador",))
        return client.call("productos", "historial", [token, action, limit])

    return internal_app(name, cluster_token, {
        action: register, "listar_ventas" if is_sale else "listar_reposiciones": history,
        "ping": lambda: {"exito": True, "servicio": name},
    })
