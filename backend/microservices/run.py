"""Arranque de un solo microservicio mediante Gunicorn."""
import os
import sys


def main():
    port = int(os.environ.get("PORT", "8080"))
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT inválido.")
    os.execv(sys.executable, [sys.executable, "-m", "gunicorn", "backend.microservices.app:create_app()",
                             "--bind", f"0.0.0.0:{port}", "--workers", "1", "--threads", "8",
                             "--timeout", "40", "--access-logfile", "-"])


if __name__ == "__main__":
    main()
