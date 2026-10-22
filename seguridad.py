import base64
import hashlib
import hmac
import json
import secrets
import time


ITERACIONES_PBKDF2 = 240_000


def _b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _b64url_dec(texto: str) -> bytes:
    relleno = "=" * (-len(texto) % 4)
    return base64.urlsafe_b64decode((texto + relleno).encode("ascii"))


def crear_hash_clave(clave: str) -> tuple[str, str]:
    if not isinstance(clave, str) or len(clave) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    salt = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac(
        "sha256", clave.encode("utf-8"), salt, ITERACIONES_PBKDF2
    )
    return _b64url(salt), _b64url(derivada)


def verificar_clave(clave: str, salt_b64: str, hash_b64: str) -> bool:
    try:
        salt = _b64url_dec(salt_b64)
        esperado = _b64url_dec(hash_b64)
    except (ValueError, TypeError):
        return False
    obtenido = hashlib.pbkdf2_hmac(
        "sha256", clave.encode("utf-8"), salt, ITERACIONES_PBKDF2
    )
    return hmac.compare_digest(obtenido, esperado)


def crear_token(usuario: str, rol: str, secreto: bytes, duracion_segundos: int) -> str:
    ahora = int(time.time())
    payload = {
        "u": usuario,
        "r": rol,
        "iat": ahora,
        "exp": ahora + int(duracion_segundos),
        "jti": secrets.token_urlsafe(12),
    }
    cuerpo = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    cuerpo_b64 = _b64url(cuerpo)
    firma = hmac.new(secreto, cuerpo_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{cuerpo_b64}.{_b64url(firma)}"


def verificar_token(token: str, secreto: bytes) -> dict:
    if not isinstance(token, str) or "." not in token:
        raise ValueError("Sesión inválida.")

    cuerpo_b64, firma_b64 = token.split(".", 1)
    firma_esperada = hmac.new(
        secreto, cuerpo_b64.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        firma_recibida = _b64url_dec(firma_b64)
    except ValueError as exc:
        raise ValueError("Sesión inválida.") from exc

    if not hmac.compare_digest(firma_esperada, firma_recibida):
        raise ValueError("Firma de sesión inválida.")

    try:
        payload = json.loads(_b64url_dec(cuerpo_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Sesión inválida.") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("La sesión expiró. Inicia sesión nuevamente.")
    if payload.get("r") not in ("vendedor", "administrador"):
        raise ValueError("Rol de sesión inválido.")
    if not payload.get("u"):
        raise ValueError("Usuario de sesión inválido.")
    return payload
