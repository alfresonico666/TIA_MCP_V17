"""Tipos de datos de usuario (UDT / PLC data types): listar, exportar y borrar.

Para CREAR un UDT se usa una fuente SCL (TYPE ... END_TYPE) con `bloques.importar_fuente`,
que es la vía más robusta en V17.
"""
from __future__ import annotations

import difflib
import uuid
from collections.abc import Iterator

from ..errores import NoEncontrado
from .sesion import SesionTia


def recorrer(plc) -> Iterator[tuple[object, str]]:
    yield from _recorrer_grupo(plc.TypeGroup, "")


def _recorrer_grupo(grupo, carpeta: str) -> Iterator[tuple[object, str]]:
    for tipo in grupo.Types:
        yield tipo, carpeta
    for subgrupo in grupo.Groups:
        yield from _recorrer_grupo(subgrupo, f"{carpeta}/{subgrupo.Name}".lstrip("/"))


def listar(plc) -> list[tuple[str, str, bool]]:
    """[(nombre, carpeta, consistente)]."""
    return [(str(t.Name), carpeta, bool(t.IsConsistent)) for t, carpeta in recorrer(plc)]


def buscar(plc, nombre: str):
    nombre = nombre.strip('"')
    for tipo, _ in recorrer(plc):
        if str(tipo.Name) == nombre:
            return tipo
    raise NoEncontrado("el UDT", nombre, difflib.get_close_matches(nombre, [str(t.Name) for t, _ in recorrer(plc)]))


def xml_de(sesion: SesionTia, tipo) -> str:
    carpeta = sesion.config.dir_trabajo
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{uuid.uuid4().hex[:8]}_udt.xml"
    try:
        tipo.Export(sesion.sis.FileInfo(str(archivo)), sesion.eng.ExportOptions.WithDefaults)
        return archivo.read_text(encoding="utf-8-sig")
    finally:
        archivo.unlink(missing_ok=True)


def borrar(plc, nombre: str) -> str:
    buscar(plc, nombre).Delete()
    return f"UDT {nombre} borrado."
