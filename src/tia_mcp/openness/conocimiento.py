"""Aprender de proyectos anteriores: exportar todo el programa (PLC y HMI) y generar un perfil de estilo.

La COPIA del proyecto se abre en modo normal (Openness V17 no permite exportar en un proyecto abierto en
solo lectura: "The operation is not permitted in a read-only context"), se exportan bloques (XML y fuente
SCL), UDT, tablas de variables y todo lo de los paneles HMI a la carpeta de conocimiento, y se cierra
SIN GUARDAR. Claude lee después `PERFIL_ESTILO.md` y los ejemplos para programar "como el equipo".
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ..analisis.estilo import perfil
from ..errores import EntradaInvalida, NoEncontrado
from ..simaticml.lector import leer_bloque
from ..simaticml.texto import bloque_como_texto
from . import bloques, hardware, hmi, proyecto, tags, tipos
from .compilacion import compilar
from .sesion import SesionTia

log = logging.getLogger(__name__)
ARCHIVO_PERFIL = "PERFIL_ESTILO.md"
_NO_PERMITIDO_EN_RUTA = re.compile(r'[<>:"/\\|?*]')


def aprender(sesion: SesionTia, ruta: str, carpeta_desarchivado: str | None = None) -> str:
    origen = Path(ruta)
    if origen.suffix.lower() == proyecto.EXTENSION_ARCHIVO:
        destino = carpeta_desarchivado or str(_primera_ruta_fija(sesion) / "_desarchivados")
        proyecto_tia = _desarchivar_sin_activar(sesion, origen, destino)
    else:
        archivo = sesion.guardia.exigir_permitida(origen)
        abiertos = [str(p.Path.FullName) for p in sesion.tia.Projects]
        if abiertos:
            raise EntradaInvalida(
                f"Para aprender hay que abrir la copia en modo normal y TIA ya tiene abierto {abiertos[0]}. "
                f"Cierra ese proyecto o conecta una instancia propia (tia_sesion conectar nueva_instancia=true).")
        proyecto_tia = sesion.tia.Projects.Open(sesion.sis.FileInfo(str(archivo)), None,
                                                sesion.eng.ProjectOpenMode.Primary)
    nombre = str(proyecto_tia.Name)
    salida = sesion.config.dir_conocimiento / _seguro(nombre)
    try:
        with sesion.proyecto_temporal(proyecto_tia):
            informe = _exportar_todo(sesion, salida, nombre)
    finally:
        proyecto_tia.Close()  # nunca se guarda: es una lectura
    return "\n".join([f"Conocimiento extraído de {nombre} en {salida}", *informe,
                      f"Lee {salida / ARCHIVO_PERFIL} antes de programar para seguir este estilo."])


def exportar_programa(sesion: SesionTia, carpeta: str) -> str:
    """Exporta el proyecto ACTIVO (XML, .scl, .txt, UDT, tags) a `carpeta`, p. ej. para versionarlo en Git."""
    destino = Path(carpeta).expanduser().absolute()
    informe = _exportar_todo(sesion, destino, str(sesion.proyecto.Name))
    return "\n".join([f"Programa exportado en {destino}", *informe])


def listar(sesion: SesionTia) -> list[str]:
    raiz = sesion.config.dir_conocimiento
    if not raiz.exists():
        return []
    return sorted(d.name for d in raiz.iterdir() if (d / ARCHIVO_PERFIL).exists())


def leer_perfil(sesion: SesionTia, nombre: str) -> str:
    archivo = sesion.config.dir_conocimiento / _seguro(nombre) / ARCHIVO_PERFIL
    if not archivo.exists():
        raise NoEncontrado("el perfil de estilo de", nombre, listar(sesion))
    return archivo.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- exportación
def _exportar_todo(sesion: SesionTia, salida: Path, nombre: str) -> list[str]:
    informe, leidos, todos_tags = [], [], []
    for _, plc in hardware.plcs(sesion):
        carpeta_plc = salida / _seguro(str(plc.Name))
        _compilar_si_hace_falta(sesion, plc)
        exportados, omitidos = 0, []
        for bloque, carpeta in bloques.recorrer(plc):
            if not bool(bloque.IsConsistent) or bool(bloque.IsKnowHowProtected):
                omitidos.append(str(bloque.Name))
                continue
            leidos.append(_exportar_bloque(sesion, plc, bloque, carpeta_plc / "bloques" / carpeta))
            exportados += 1
        for udt, carpeta in tipos.recorrer(plc):
            _guardar(carpeta_plc / "udt" / carpeta / f"{_seguro(str(udt.Name))}.xml", tipos.xml_de(sesion, udt))
        for tabla, carpeta in tags.recorrer_tablas(plc):
            destino = carpeta_plc / "tags" / carpeta / f"{_seguro(str(tabla.Name))}.xml"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.unlink(missing_ok=True)
            tabla.Export(sesion.sis.FileInfo(str(destino)), sesion.eng.ExportOptions.WithDefaults)
        todos_tags += tags.todos(sesion, plc)
        informe.append(f"  {plc.Name}: {exportados} bloques exportados"
                       + (f"; omitidos (inconsistentes/protegidos): {', '.join(omitidos)}" if omitidos else ""))
    try:
        for _, panel in hmi.paneles(sesion):
            informe += hmi.exportar(sesion, panel, salida / "HMI" / _seguro(str(panel.Name)))
    except Exception as e:  # la HMI es un extra: no debe impedir aprender el PLC
        log.warning("No se pudo exportar la HMI: %s", e)
        informe.append(f"  HMI: no exportada ({e})")
    _guardar(salida / ARCHIVO_PERFIL, perfil(nombre, leidos, todos_tags))
    return informe


def _compilar_si_hace_falta(sesion: SesionTia, plc) -> None:
    """TIA no exporta bloques inconsistentes. En proyectos abiertos en solo lectura compilar puede no
    estar permitido: en ese caso se exporta lo que ya es consistente y el resto se informa como omitido."""
    if all(bool(b.IsConsistent) for b, _ in bloques.recorrer(plc)):
        return
    try:
        compilar(sesion, plc)
    except Exception as e:  # el proyecto en solo lectura no admite compilar
        log.info("No se pudo compilar antes de exportar (%s); se exporta lo consistente.", e)


def _exportar_bloque(sesion: SesionTia, plc, bloque, carpeta: Path):
    nombre = _seguro(str(bloque.Name))
    xml = bloques.xml_de(sesion, bloque)
    _guardar(carpeta / f"{nombre}.xml", xml)
    leido = leer_bloque(xml)
    if str(bloque.ProgrammingLanguage) in bloques.LENGUAJES_CON_FUENTE:
        try:
            _guardar(carpeta / f"{nombre}{bloques.extension_fuente(bloque)}", bloques.fuente_de(sesion, plc, bloque))
        except Exception as e:
            log.warning("Sin fuente para %s: %s", nombre, e)
    _guardar(carpeta / f"{nombre}.txt", bloque_como_texto(leido) + "\n")
    return leido


def _desarchivar_sin_activar(sesion: SesionTia, zap: Path, carpeta: str):
    destino = sesion.guardia.exigir_permitida(Path(carpeta) / zap.stem)
    if destino.exists() and any(destino.iterdir()):
        raise EntradaInvalida(f"Ya existe {destino}: ábrelo con su .ap17 o borra esa copia.")
    return sesion.tia.Projects.Retrieve(sesion.sis.FileInfo(str(zap)), sesion.sis.DirectoryInfo(str(destino)))


def _primera_ruta_fija(sesion: SesionTia) -> Path:
    for patron in sesion.guardia.patrones:
        if not any(c in patron for c in "*?["):
            return Path(patron).expanduser()
    raise EntradaInvalida("Indica carpeta_desarchivado: no hay una ruta permitida sin comodines.")


def _guardar(archivo: Path, contenido: str) -> None:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(contenido, encoding="utf-8")


def _seguro(nombre: str) -> str:
    return _NO_PERMITIDO_EN_RUTA.sub("_", nombre)

