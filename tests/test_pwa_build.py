import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preparar_pwa


class PruebasVersionPWA(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        frontend = self.root / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<html>InvAx</html>")
        (frontend / "sw.js").write_text("const VERSION='invax-shell-inicial';\nconst SHELL=['/'];\n")
        self.patcher = patch.object(preparar_pwa, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def ejecutar(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()):
            preparar_pwa.preparar(check)
        return (self.root / "frontend/sw.js").read_text()

    def test_version_estable_y_cambia_con_el_recurso(self):
        antes = self.ejecutar()
        self.assertEqual(antes, self.ejecutar())
        self.assertEqual(antes, self.ejecutar(check=True))
        (self.root / "frontend/index.html").write_text("<html>Nueva versión</html>")
        with self.assertRaises(SystemExit):
            self.ejecutar(check=True)
        self.assertNotEqual(antes, self.ejecutar())

    def test_version_cambia_si_cambia_la_logica_del_worker(self):
        antes = self.ejecutar()
        worker = self.root / "frontend/sw.js"
        worker.write_text(antes + "// Lógica de caché actualizada\n")
        self.assertNotEqual(antes.splitlines()[0], self.ejecutar().splitlines()[0])

    def test_recurso_faltante_no_reescribe_el_worker(self):
        worker = self.root / "frontend/sw.js"
        antes = worker.read_text()
        (self.root / "frontend/index.html").unlink()
        with self.assertRaises(FileNotFoundError):
            self.ejecutar()
        self.assertEqual(antes, worker.read_text())
