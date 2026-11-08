"""Paneles HMI (WinCC Basic/Comfort, p. ej. KTP400 Basic): agregar, red, exportar, importar y compilar.

Límites de Openness V17 (documentación oficial, comprobados en vivo):
  - NO puede crear la **conexión HMI integrada** (HMI_Connection_1, acceso simbólico al PLC). Se crea una vez
    a mano en "Dispositivos y redes" y se reutiliza desde un proyecto/plantilla base.
  - NO expone la **pantalla de inicio** del runtime: se elige una vez a mano.
  - Visor de alarmas, popups y alarmas HMI no se pueden importar en paneles Basic.
  - Un import fallido puede dejar inválidos (disposed) los objetos del proyecto: se detecta y se avisa.
"""
from __future__ import annotations

import difflib
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errores import EntradaInvalida, ErrorTia, NoEncontrado, OperacionTiaFallida
from ..simaticml.hmi.lector import leer_pantalla, leer_tabla_tags, pantalla_como_texto, tabla_tags_como_texto
from . import red
from .cargador import implementacion, tipo_hmi_target
from .compilacion import MensajeCompilacion, ResultadoCompilacion, compilar
from .hardware import items_recursivos, todos_los_dispositivos
from .proyecto import detalle_error
from .sesion import SesionTia

log = logging.getLogger(__name__)
TIPOS_IMPORTABLES = ("pantalla", "plantilla", "tags", "lista_textos", "conexion")
_SEGURO = re.compile(r'[<>:"/\\|?*]')
INSTRUCCIONES_CONEXION = (
    "Openness V17 no puede crear la conexión HMI integrada. Hazlo UNA vez en TIA: 'Dispositivos y redes' → "
    "vista de redes → botón 'Conexiones' → tipo 'Conexión HMI' → arrastra del puerto PROFINET del panel al del "
    "PLC (se crea 'HMI_Connection_1'). Después, en el panel: 'Configuración de runtime' → 'General' → "
    "'Pantalla inicial'. Guarda y vuelve a ejecutar. Consejo: guarda ese proyecto como plantilla base (.zap17).")


@dataclass(frozen=True)
class ContenidoHmi:
    panel: str
    pantallas: list[str]
    plantillas: list[str]
    tablas_tags: list[str]
    listas_textos: list[str]
    conexiones: list[str]


# --------------------------------------------------------------------------- localizar
def paneles(sesion: SesionTia) -> list[tuple[object, object]]:
    """[(dispositivo, HmiTarget)] de todo el proyecto."""
    HmiTarget = tipo_hmi_target(sesion.config)
    resultado = []
    for dispositivo in todos_los_dispositivos(sesion.proyecto):
        for item in items_recursivos(dispositivo.DeviceItems):
            contenedor = item.GetService[sesion.eng.SoftwareContainer]()
            if contenedor is None:
                continue
            software = implementacion(contenedor.Software)
            if isinstance(software, HmiTarget):
                resultado.append((dispositivo, software))
    return resultado


def panel(sesion: SesionTia, nombre: str | None = None):
    """HmiTarget por nombre del dispositivo (HMI_1) o del software (HMI_RT_1); opcional si hay uno solo."""
    encontrados = paneles(sesion)
    if not encontrados:
        raise NoEncontrado("ningún panel HMI en el proyecto", "", None)
    if nombre is None:
        if len(encontrados) > 1:
            nombres = ", ".join(str(d.Name) for d, _ in encontrados)
            raise EntradaInvalida(f"Hay varios paneles; indica `panel` ({nombres}).")
        return encontrados[0][1]
    for dispositivo, hmi in encontrados:
        if nombre in (str(dispositivo.Name), str(hmi.Name)):
            return hmi
    nombres = [str(d.Name) for d, _ in encontrados]
    raise NoEncontrado("el panel", nombre, difflib.get_close_matches(nombre, nombres))


def contenido(hmi) -> ContenidoHmi:
    return ContenidoHmi(
        panel=str(hmi.Name),
        pantallas=["/".join(r) for _, r in _recorrer(hmi.ScreenFolder, "Screens")],
        plantillas=["/".join(r) for _, r in _recorrer(hmi.ScreenTemplateFolder, "ScreenTemplates")],
        tablas_tags=["/".join(r) for _, r in _recorrer(hmi.TagFolder, "TagTables")],
        listas_textos=[str(t.Name) for t in hmi.TextLists],
        conexiones=[str(c.Name) for c in hmi.Connections] or ["(ninguna visible: las integradas no se listan)"],
    )


def culturas_proyecto(sesion: SesionTia) -> tuple[str, ...]:
    """Idiomas activos del proyecto, el de edición primero. Los textos HMI se generan en todos: si el runtime
    arranca en un idioma sin texto, el panel mostraría campos vacíos."""
    ajustes = sesion.proyecto.LanguageSettings
    edicion = str(ajustes.EditingLanguage.Culture.Name)
    activos = [str(idioma.Culture.Name) for idioma in ajustes.ActiveLanguages]
    return tuple(dict.fromkeys([edicion, *activos]))


# --------------------------------------------------------------------------- hardware
def agregar_panel(sesion: SesionTia, nombre: str, referencia: str) -> str:
    """referencia: '6AV2 123-2DB03-0AX0/17.0.0.0' (KTP400 Basic PN, imagen V17)."""
    if "/" not in referencia:
        raise EntradaInvalida("La referencia debe incluir la versión, p. ej. '6AV2 123-2DB03-0AX0/17.0.0.0'.")
    return red.agregar_dispositivo(sesion, nombre, referencia)


def conectar_a_plc(sesion: SesionTia, nombre_panel: str, nombre_plc: str, subred: str = red.SUBRED_POR_DEFECTO) -> str:
    lineas = [red.conectar_subred(sesion, nombre_plc, subred), red.conectar_subred(sesion, nombre_panel, subred),
              f"Siguiente paso MANUAL (una vez): {INSTRUCCIONES_CONEXION}"]
    return "\n".join(lineas)


# --------------------------------------------------------------------------- exportar / leer
def exportar(sesion: SesionTia, hmi, carpeta: Path) -> list[str]:
    """Pantallas, plantillas, tablas de tags, listas de textos y conexiones (no integradas) a XML."""
    informe, errores = [], []
    grupos = (("pantallas", hmi.ScreenFolder, "Screens"), ("plantillas", hmi.ScreenTemplateFolder, "ScreenTemplates"),
              ("tags", hmi.TagFolder, "TagTables"))
    cuentas = {}
    for subcarpeta, raiz, coleccion in grupos:
        cuentas[subcarpeta] = 0
        for objeto, partes in _recorrer(raiz, coleccion):
            destino = carpeta.joinpath(subcarpeta, *[_seguro(p) for p in partes[:-1]], f"{_seguro(partes[-1])}.xml")
            if _exportar_objeto(sesion, objeto, destino, errores):
                cuentas[subcarpeta] += 1
    for subcarpeta, coleccion in (("listas_texto", hmi.TextLists), ("listas_graficos", hmi.GraphicLists),
                                  ("conexiones", hmi.Connections)):
        cuentas[subcarpeta] = sum(_exportar_objeto(sesion, o, carpeta / subcarpeta / f"{_seguro(str(o.Name))}.xml",
                                                   errores) for o in coleccion)
    informe.append(f"  HMI {hmi.Name}: " + ", ".join(f"{k} {v}" for k, v in cuentas.items()))
    informe += [f"    no exportado: {e}" for e in errores]
    return informe


def leer(sesion: SesionTia, hmi, tipo: str, nombre: str) -> str:
    objeto = _buscar(hmi, tipo, nombre)
    temporal = Path(tempfile.gettempdir()) / "tia_mcp" / f"hmi_{_seguro(nombre)}.xml"
    errores: list[str] = []
    if not _exportar_objeto(sesion, objeto, temporal, errores):
        raise OperacionTiaFallida(f"No se pudo exportar {tipo} '{nombre}': {errores[0]}")
    xml = temporal.read_bytes()
    if tipo == "tags":
        return tabla_tags_como_texto(*leer_tabla_tags(xml))
    return pantalla_como_texto(leer_pantalla(xml))


def xml_de(sesion: SesionTia, hmi, tipo: str, nombre: str) -> str:
    objeto = _buscar(hmi, tipo, nombre)
    temporal = Path(tempfile.gettempdir()) / "tia_mcp" / f"hmi_{_seguro(nombre)}.xml"
    errores: list[str] = []
    if not _exportar_objeto(sesion, objeto, temporal, errores):
        raise OperacionTiaFallida(f"No se pudo exportar {tipo} '{nombre}': {errores[0]}")
    return temporal.read_text(encoding="utf-8-sig")


# --------------------------------------------------------------------------- importar
def importar(sesion: SesionTia, hmi, tipo: str, xml: str) -> list[str]:
    """Importa (reemplazando si existe) una pantalla, plantilla, tabla de tags, lista de textos o conexión."""
    if tipo not in TIPOS_IMPORTABLES:
        raise EntradaInvalida(f"tipo '{tipo}' no válido. Usa: {', '.join(TIPOS_IMPORTABLES)}.")
    composicion = {"pantalla": hmi.ScreenFolder.Screens, "plantilla": hmi.ScreenTemplateFolder.ScreenTemplates,
                   "tags": hmi.TagFolder.TagTables, "lista_textos": hmi.TextLists,
                   "conexion": hmi.Connections}[tipo]
    archivo = Path(tempfile.gettempdir()) / "tia_mcp" / f"importar_hmi_{tipo}.xml"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(xml, encoding="utf-8")
    try:
        importados = composicion.Import(sesion.sis.FileInfo(str(archivo)), sesion.eng.ImportOptions.Override)
    except Exception as e:
        raise _error_importacion(sesion, tipo, e) from e
    return [str(o.Name) for o in importados]


def _error_importacion(sesion: SesionTia, tipo: str, error: Exception) -> ErrorTia:
    detalle = detalle_error(error)
    texto = str(error)
    proyecto_invalido = False
    try:
        _ = sesion.proyecto.Name
    except Exception:
        proyecto_invalido = True
        sesion.olvidar_proyecto()
    aviso = (" AVISO: tras el error TIA invalidó el proyecto en esta sesión; vuelve a abrirlo con "
             "tia_proyecto action='abrir'." if proyecto_invalido else "")
    conexion = re.search(r"Connection (\S+) of the (\S+) tag was not found", texto)
    if conexion:
        return OperacionTiaFallida(f"La conexión '{conexion.group(1)}' no existe en el panel (tag "
                                   f"{conexion.group(2)}). {INSTRUCCIONES_CONEXION}{aviso}")
    if "already exists" in texto:
        return OperacionTiaFallida(
            f"TIA rechazó la importación de {tipo}: ya existe un objeto con ese nombre. Los tags HMI deben tener "
            f"nombre ÚNICO en todas las tablas del panel (reemplazar solo funciona dentro de la misma tabla): usa "
            f"otro nombre o importa en la tabla donde ya está.{aviso}")
    return OperacionTiaFallida(f"TIA rechazó la importación de {tipo}: {detalle}{aviso}")


# --------------------------------------------------------------------------- compilar
def compilar_panel(sesion: SesionTia, hmi) -> ResultadoCompilacion:
    resultado = compilar(sesion, hmi)
    if any("start screen" in m.texto.lower() for m in resultado.mensajes):
        resultado.mensajes.append(MensajeCompilacion(
            gravedad="Info", ubicacion=str(hmi.Name),
            texto="Falta la pantalla inicial: Openness no la expone; elígela en 'Configuración de runtime'."))
    return resultado


# --------------------------------------------------------------------------- internos
def _recorrer(carpeta, coleccion: str, ruta: tuple[str, ...] = ()):
    """(objeto, (carpeta, ..., nombre)): tupla porque un nombre puede contener '/' (p. ej. pantalla 'E/S')."""
    for objeto in getattr(carpeta, coleccion):
        yield objeto, (*ruta, str(objeto.Name))
    for sub in carpeta.Folders:
        yield from _recorrer(sub, coleccion, (*ruta, str(sub.Name)))


def _buscar(hmi, tipo: str, nombre: str):
    origen = {"pantalla": (hmi.ScreenFolder, "Screens"), "plantilla": (hmi.ScreenTemplateFolder, "ScreenTemplates"),
              "tags": (hmi.TagFolder, "TagTables")}
    if tipo == "lista_textos":
        objeto = hmi.TextLists.Find(nombre)
        if objeto is None:
            raise NoEncontrado("la lista de textos", nombre, [str(t.Name) for t in hmi.TextLists])
        return objeto
    if tipo not in origen:
        raise EntradaInvalida(f"tipo '{tipo}' no válido para leer. Usa: pantalla, plantilla, tags, lista_textos.")
    todos = list(_recorrer(*origen[tipo]))
    for objeto, partes in todos:
        if nombre in (str(objeto.Name), "/".join(partes)):
            return objeto
    raise NoEncontrado(f"{tipo} del panel", nombre,
                       difflib.get_close_matches(nombre, [str(o.Name) for o, _ in todos]))


def _exportar_objeto(sesion: SesionTia, objeto, destino: Path, errores: list[str]) -> bool:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)  # Export no sobrescribe
    try:
        objeto.Export(sesion.sis.FileInfo(str(destino)), sesion.eng.ExportOptions.WithDefaults)
        return True
    except Exception as e:
        errores.append(f"{destino.name}: {detalle_error(e)}")
        log.warning("No se exportó %s: %s", destino, e)
        return False


def _seguro(nombre: str) -> str:
    return _SEGURO.sub("_", nombre)
