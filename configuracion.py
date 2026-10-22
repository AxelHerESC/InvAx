import base64
import json
import os
import secrets
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("INVENTARIO_DATA_DIR", str(BASE_DIR)))
RUTA_BD = DATA_DIR / "inventario.db"
RUTA_SEGURIDAD_SERVIDOR = DATA_DIR / ".seguridad_servidor.json"
RUTA_CLAVE_CLIENTE = DATA_DIR / ".clave_cliente"

SERVIDORES = [
    ("S1", "127.0.0.1", 5100),
    ("S2", "127.0.0.1", 5101),
    ("S3", "127.0.0.1", 5102),
]

NOMBRE_OBJETO_REMOTO = "obtener_servicio_inventario"
DURACION_SESION_SEGUNDOS = 15 * 60
MAX_CANTIDAD_OPERACION = 10000
MAX_INTENTOS_LOGIN = 5
BLOQUEO_LOGIN_SEGUNDOS = 30

USUARIO_ADMIN_INICIAL = "admin"
USUARIO_VENDEDOR_INICIAL = "vendedor"
CLAVE_ADMIN_INICIAL = os.environ.get("INVENTARIO_ADMIN_PASSWORD", "Admin2026!")
CLAVE_VENDEDOR_INICIAL = os.environ.get("INVENTARIO_VENDEDOR_PASSWORD", "Venta2026!")


def _guardar_privado(ruta: Path, contenido: str):
    ruta.write_text(contenido, encoding="utf-8")
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


def _secretos_entorno():
    authkey = os.environ.get("INVENTARIO_AUTHKEY")
    token_secret = os.environ.get("INVENTARIO_TOKEN_SECRET")
    if not authkey and not token_secret:
        return None
    if not authkey or not token_secret or len(authkey) < 32 or len(token_secret) < 32:
        raise ValueError("Configura INVENTARIO_AUTHKEY e INVENTARIO_TOKEN_SECRET con al menos 32 caracteres cada uno.")
    return {"authkey": authkey.encode("utf-8"), "token_secret": token_secret.encode("utf-8")}


def preparar_secretos():
    """Crea secretos compartidos una sola vez y devuelve la configuración del servidor."""
    secretos = _secretos_entorno()
    if secretos:
        return secretos
    if RUTA_SEGURIDAD_SERVIDOR.exists() and RUTA_CLAVE_CLIENTE.exists():
        return cargar_secretos_servidor()

    authkey = secrets.token_bytes(32)
    token_secret = secrets.token_bytes(32)
    authkey_b64 = base64.urlsafe_b64encode(authkey).decode("ascii")
    token_b64 = base64.urlsafe_b64encode(token_secret).decode("ascii")

    _guardar_privado(
        RUTA_SEGURIDAD_SERVIDOR,
        json.dumps(
            {"authkey": authkey_b64, "token_secret": token_b64},
            indent=2,
        ),
    )
    _guardar_privado(RUTA_CLAVE_CLIENTE, authkey_b64 + "\n")
    return {"authkey": authkey, "token_secret": token_secret}


def cargar_secretos_servidor():
    secretos = _secretos_entorno()
    if secretos:
        return secretos
    if not RUTA_SEGURIDAD_SERVIDOR.exists():
        raise FileNotFoundError(
            "No existe la configuración de seguridad. Ejecuta iniciar_cluster.py primero."
        )
    datos = json.loads(RUTA_SEGURIDAD_SERVIDOR.read_text(encoding="utf-8"))
    return {
        "authkey": base64.urlsafe_b64decode(datos["authkey"].encode("ascii")),
        "token_secret": base64.urlsafe_b64decode(datos["token_secret"].encode("ascii")),
    }


def cargar_authkey_cliente():
    authkey = os.environ.get("INVENTARIO_AUTHKEY")
    if authkey:
        if len(authkey) < 32:
            raise ValueError("INVENTARIO_AUTHKEY debe tener al menos 32 caracteres.")
        return authkey.encode("utf-8")
    if not RUTA_CLAVE_CLIENTE.exists():
        raise FileNotFoundError(
            "No existe la clave de conexión. Ejecuta iniciar_cluster.py primero."
        )
    return base64.urlsafe_b64decode(
        RUTA_CLAVE_CLIENTE.read_text(encoding="utf-8").strip().encode("ascii")
    )
