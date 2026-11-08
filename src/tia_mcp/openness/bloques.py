"""Bloques del PLC: listar, buscar, exportar (XML / fuente SCL), importar, borrar."""
from __future__ import annotations

import difflib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..errores import NoEncontrado, OperacionTiaFallida
from .cargador import implementacion
from .compilacion import ResultadoCompilacion, compilar
from .sesion import SesionTia

LENGUAJES_CON_FUENTE = frozenset({"SCL", "STL", "DB"})


@dataclass(frozen=True)
class InfoBloque:
    nombre: str
    tipo: str          # OB, FB, FC, GlobalDB, InstanceDB, ArrayDB
    numero: int
    lenguaje: str
    consistente: bool
    carpeta: str
    instancia_de: str | None = None


# --------------------------------------------------------------------------- recorrido
def recorrer(plc) -> Iterator[tuple[object, str]]:
    """(bloque, carpeta) de todos los bloques, incluidas carpetas de usuario."""
    yield from _recorrer_grupo(plc.BlockGroup, "")


def _recorrer_grupo(grupo, carpeta: str) -> Iterator[tuple[object, str]]:
    for bloque in grupo.Blocks:
        yield bloque, carpeta
    for subgrupo in grupo.Groups:
        yield from _recorrer_grupo(subgrupo, f"{carpeta}/{subgrupo.Name}".lstrip("/"))


def info(bloque, carpeta: str = "") -> InfoBloque:
    concreto = implementacion(bloque)
    return InfoBloque(nombre=str(bloque.Name), tipo=concreto.GetType().Name, numero=int(bloque.Number),
                      lenguaje=str(bloque.ProgrammingLanguage), consistente=bool(bloque.IsConsistent),
                      carpeta=carpeta, instancia_de=_instancia_de(concreto))


def listar(plc) -> list[InfoBloque]:
    return [info(b, c) for b, c in recorrer(plc)]


def buscar(plc, nombre: str):
    for bloque, _ in recorrer(plc):
        if str(bloque.Name) == nombre:
            return bloque
    nombres = [str(b.Name) for b, _ in recorrer(plc)]
    raise NoEncontrado("el bloque", nombre, difflib.get_close_matches(nombre, nombres, n=5))


def grupo_por_ruta(plc, carpeta: str | None, crear: bool = False):
    """Grupo de bloques por ruta 'Motores/Bombas'; None o '' = raíz."""
    grupo = plc.BlockGroup
    for parte in [p for p in (carpeta or "").split("/") if p]:
        siguiente = grupo.Groups.Find(parte)
        if siguiente is None:
            if not crear:
                raise NoEncontrado("la carpeta de bloques", parte)
            siguiente = grupo.Groups.Create(parte)
        grupo = siguiente
    return grupo


# --------------------------------------------------------------------------- exportar
def exportar_xml(sesion: SesionTia, bloque, destino: Path) -> Path:
    asegurar_consistente(sesion, bloque)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)  # Export() no sobrescribe
    bloque.Export(sesion.sis.FileInfo(str(destino)), sesion.eng.ExportOptions.WithDefaults)
    return destino


def xml_de(sesion: SesionTia, bloque) -> str:
    temporal = _archivo_temporal(sesion, ".xml")
    try:
        return exportar_xml(sesion, bloque, temporal).read_text(encoding="utf-8-sig")
    finally:
        temporal.unlink(missing_ok=True)


def fuente_de(sesion: SesionTia, plc, bloque) -> str:
    """Fuente SCL/STL/DB generada por TIA (KOP/FUP no tienen fuente de texto)."""
    asegurar_consistente(sesion, bloque)
    temporal = _archivo_temporal(sesion, extension_fuente(bloque))
    lista = sesion.sis.List[sesion.eng.PlcBlock]()
    lista.Add(bloque)
    sin_opciones = getattr(sesion.eng.GenerateOptions, "None")  # "None" es palabra reservada en Python
    try:
        plc.ExternalSourceGroup.GenerateSource(lista, sesion.sis.FileInfo(str(temporal)), sin_opciones)
        return temporal.read_text(encoding="utf-8-sig")
    finally:
        temporal.unlink(missing_ok=True)


def extension_fuente(bloque) -> str:
    """TIA exige la extensión según el tipo: .db para DB, .awl para STL, .scl para el resto."""
    if implementacion(bloque).GetType().Name in ("GlobalDB", "InstanceDB", "ArrayDB"):
        return ".db"
    return ".awl" if str(bloque.ProgrammingLanguage) == "STL" else ".scl"


def asegurar_consistente(sesion: SesionTia, bloque) -> None:
    """TIA no exporta bloques inconsistentes: se compila el bloque si hace falta."""
    if bool(bloque.IsConsistent):
        return
    resultado = compilar(sesion, bloque)
    if not resultado.correcto:
        raise OperacionTiaFallida(f"El bloque {bloque.Name} no compila, no se puede exportar.\n"
                                  f"{resultado.resumen()}")


# --------------------------------------------------------------------------- importar
def importar_xml(sesion: SesionTia, plc, archivo: Path, carpeta: str | None = None) -> list[str]:
    grupo = grupo_por_ruta(plc, carpeta, crear=True)
    try:
        importados = grupo.Blocks.Import(sesion.sis.FileInfo(str(archivo)), sesion.eng.ImportOptions.Override)
    except Exception as e:
        raise OperacionTiaFallida(f"TIA rechazó la importación de {archivo.name}: {e}") from e
    return [str(b.Name) for b in importados]


def importar_fuente(sesion: SesionTia, plc, archivo: Path, carpeta: str | None = None) -> list[str]:
    """Importa un .scl/.db/.udt como fuente externa, genera los bloques y borra la fuente."""
    fuentes = plc.ExternalSourceGroup.ExternalSources
    nombre_fuente = archivo.name
    existente = fuentes.Find(nombre_fuente)
    if existente is not None:
        existente.Delete()
    fuente = fuentes.CreateFromFile(nombre_fuente, str(archivo))
    try:
        opcion = sesion.eng.GenerateBlockOption.KeepOnError
        if carpeta:
            generados = fuente.GenerateBlocksFromSource(grupo_por_ruta(plc, carpeta, crear=True), opcion)
        else:
            generados = fuente.GenerateBlocksFromSource(opcion)
        return [str(implementacion(g).Name) for g in generados]  # vienen como IEngineeringObject
    except Exception as e:
        raise OperacionTiaFallida(f"TIA no pudo generar bloques desde la fuente: {e}") from e
    finally:
        fuente.Delete()


def crear_db_instancia(plc, nombre_db: str, nombre_fb: str, numero: int | None = None) -> str:
    plc.BlockGroup.Blocks.CreateInstanceDB(nombre_db, numero is None, numero or 1, nombre_fb)
    return f"DB de instancia {nombre_db} creado para {nombre_fb}."


def borrar(bloque) -> str:
    nombre = str(bloque.Name)
    bloque.Delete()
    return f"Bloque {nombre} borrado."


# --------------------------------------------------------------------------- respaldo
class RespaldoBloques:
    """Exporta bloques antes de sobrescribirlos para poder restaurarlos si algo falla."""

    def __init__(self, sesion: SesionTia, plc, nombres: list[str]) -> None:
        self._sesion, self._plc = sesion, plc
        self._copias: dict[str, tuple[Path, str]] = {}
        for bloque, carpeta in recorrer(plc):
            if str(bloque.Name) in nombres and bool(bloque.IsConsistent):
                destino = _archivo_temporal(sesion, f"_{bloque.Name}.xml")
                exportar_xml(sesion, bloque, destino)
                self._copias[str(bloque.Name)] = (destino, carpeta)

    @property
    def respaldados(self) -> list[str]:
        return list(self._copias)

    def restaurar(self) -> list[str]:
        restaurados = []
        for nombre, (archivo, carpeta) in self._copias.items():
            importar_xml(self._sesion, self._plc, archivo, carpeta)
            restaurados.append(nombre)
        return restaurados

    def descartar(self) -> None:
        for archivo, _ in self._copias.values():
            archivo.unlink(missing_ok=True)
        self._copias.clear()


def compilar_plc(sesion: SesionTia, plc) -> ResultadoCompilacion:
    return compilar(sesion, plc)


def _instancia_de(bloque) -> str | None:
    try:
        return str(bloque.InstanceOfName) or None
    except AttributeError:
        return None


def _archivo_temporal(sesion: SesionTia, sufijo: str) -> Path:
    carpeta = sesion.config.dir_trabajo
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / f"{uuid.uuid4().hex[:8]}{sufijo}"
