"""Validación de SimaticML contra los XSD oficiales que instala TIA V17.

Los XSD de Siemens no declaran targetNamespace, así que se quita el namespace de
cada fragmento (FlgNet, Sections) antes de validarlo.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path

from lxml import etree

from .xml_util import local

_XSD_FLGNET = "SW.PlcBlocks.LADFBD_v4.xsd"
_XSD_INTERFAZ = "SW.InterfaceSections_v4.xsd"


class ValidadorXsd:
    def __init__(self, dir_esquemas: Path) -> None:
        self._dir = dir_esquemas

    @property
    def disponible(self) -> bool:
        return (self._dir / _XSD_FLGNET).exists()

    def errores(self, xml: str) -> list[str]:
        """Lista de errores (vacía si es válido). Si no hay XSD instalados, no valida."""
        if not self.disponible:
            return []
        documento = etree.fromstring(xml.encode("utf-8"))
        problemas: list[str] = []
        for indice, red in enumerate(_buscar(documento, "FlgNet"), start=1):
            problemas += [f"Red {indice}: {e}" for e in self._validar(_XSD_FLGNET, red)]
        for secciones in _buscar(documento, "Sections"):
            problemas += [f"Interfaz: {e}" for e in self._validar(_XSD_INTERFAZ, secciones)]
        return problemas

    def _validar(self, xsd: str, elemento) -> list[str]:
        esquema = _esquema(self._dir / xsd)
        limpio = _sin_namespace(elemento)
        if esquema.validate(limpio):
            return []
        return [f"línea {e.line}: {e.message}" for e in esquema.error_log]


@cache
def _esquema(ruta: Path) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(ruta)))


def _buscar(documento, nombre: str) -> list:
    return [e for e in documento.iter() if isinstance(e.tag, str) and local(e) == nombre
            and (nombre != "Sections" or local(e.getparent()) == "Interface")]


def _sin_namespace(elemento):
    copia = etree.fromstring(etree.tostring(elemento))
    for e in copia.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]
    etree.cleanup_namespaces(copia)
    return copia
