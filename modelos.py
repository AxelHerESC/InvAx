from dataclasses import dataclass


@dataclass(frozen=True)
class Producto:
    """Vista inmutable de un producto almacenado en el inventario."""

    id_producto: str
    nombre: str
    precio: float
    cantidad: int
    version: int = 0

    def a_diccionario(self):
        return {
            "id": self.id_producto,
            "nombre": self.nombre,
            "precio": self.precio,
            "cantidad": self.cantidad,
            "version": self.version,
        }
