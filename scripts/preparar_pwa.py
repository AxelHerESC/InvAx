"""Deriva la versión de caché del contenido real, sin dependencias de compilación."""
import argparse
import ast
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

def preparar(check=False):
    frontend = ROOT / "frontend"
    worker = frontend / "sw.js"
    texto = worker.read_text(encoding="utf-8")
    recursos = ast.literal_eval(re.search(r"const SHELL=(\[.*?\]);", texto, re.S).group(1))
    resumen = hashlib.sha256()
    for url in sorted(recursos):
        relativo = "index.html" if url == "/" else url.removeprefix("/assets/") if url.startswith("/assets/") else url.lstrip("/")
        archivo = frontend / relativo
        resumen.update(url.encode("utf-8") + b"\0" + archivo.read_bytes() + b"\0")
    plantilla = re.sub(r"const VERSION='[^']+';", "const VERSION='CONTENIDO';", texto)
    resumen.update(plantilla.encode("utf-8"))
    version = "invax-shell-" + resumen.hexdigest()[:16]
    actualizado = re.sub(r"const VERSION='[^']+';", f"const VERSION='{version}';", texto)
    if check and actualizado != texto:
        raise SystemExit("La versión PWA está desactualizada. Ejecuta python scripts/preparar_pwa.py")
    if not check:
        worker.write_text(actualizado, encoding="utf-8")
    print(version)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    preparar(parser.parse_args().check)
