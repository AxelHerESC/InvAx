"""Configuración administrativa explícita; no se ejecuta al arrancar servicios."""
from getpass import getpass
from pathlib import Path
import os
import psycopg
from psycopg import sql


def main():
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        raise SystemExit("Configura ADMIN_DATABASE_URL en tu entorno privado, nunca en Git.")
    password = getpass("Contraseña administrativa de PostgreSQL: ")
    with psycopg.connect(url, password=password, sslmode="require", connect_timeout=8) as c:
        c.execute((Path(__file__).resolve().parent.parent / "database/02_microservices.sql").read_text())
        for role in ("invax_auth", "invax_productos"):
            value = getpass(f"Nueva contraseña privada para {role}: ")
            if len(value) < 16 or value != getpass("Confirmación: "):
                raise SystemExit("Contraseña corta o confirmación distinta. Configuración interrumpida.")
            c.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(value)))
    print("Roles preparados. Guarda sus contraseñas directamente en el alojamiento.")


if __name__ == "__main__":
    main()
