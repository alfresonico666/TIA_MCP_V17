"""Operaciones de proyecto: abrir, crear, desarchivar, guardar, cerrar, archivar."""
from __future__ import annotations

import re
import time
from pathlib import Path

from ..errores import EntradaInvalida, ErrorTia, OperacionTiaFallida
from .sesion import SesionTia, ruta_proyecto

_NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_\-]+$")  # TIA falla con nombres no ASCII
_INTENTOS_ARCHIVAR = 3
_ESPERA_ENTRE_INTENTOS_S = 3
EXTENSION_PROYECTO = ".ap17"
EXTENSION_ARCHIVO = ".zap17"


def abrir(sesion: SesionTia, ruta: str, solo_lectura: bool = False) -> str:
    archivo = sesion.guardia.exigir_permitida(ruta)
    if archivo.suffix.lower() != EXTENSION_PROYECTO:
        raise EntradaInvalida(f"Se esperaba un archivo {EXTENSION_PROYECTO}: {archivo}")
    if not archivo.exists():
        raise EntradaInvalida(f"No existe {archivo}")
    ya_abierto = _proyecto_abierto_en(sesion, archivo)
    if ya_abierto is not None:
        sesion.usar_proyecto(ya_abierto)
        return f"El proyecto ya estaba abierto en TIA: {archivo}"
    if not solo_lectura:
        _exigir_sin_proyecto_principal(sesion)
    modo = sesion.eng.ProjectOpenMode.Secondary if solo_lectura else sesion.eng.ProjectOpenMode.Primary
    proyecto = sesion.tia.Projects.Open(sesion.sis.FileInfo(str(archivo)), None, modo)
    sesion.usar_proyecto(proyecto)
    return f"Proyecto abierto{' en SOLO LECTURA' if solo_lectura else ''}: {archivo}"


def crear(sesion: SesionTia, carpeta: str, nombre: str) -> str:
    _exigir_nombre_valido(nombre)
    destino = sesion.guardia.exigir_permitida(carpeta)
    if (destino / nombre).exists():
        raise EntradaInvalida(f"Ya existe {destino / nombre}. Ábrelo con action='abrir'.")
    _exigir_sin_proyecto_principal(sesion)
    destino.mkdir(parents=True, exist_ok=True)
    proyecto = sesion.tia.Projects.Create(sesion.sis.DirectoryInfo(str(destino)), nombre)
    sesion.usar_proyecto(proyecto)
    return f"Proyecto creado: {ruta_proyecto(proyecto)}"


def desarchivar(sesion: SesionTia, archivo_zap: str, carpeta_destino: str) -> str:
    """El .zap17 puede estar en cualquier lado: desarchivar crea una COPIA en una ruta permitida."""
    zap = Path(archivo_zap)
    if zap.suffix.lower() != EXTENSION_ARCHIVO or not zap.exists():
        raise EntradaInvalida(f"No existe el archivo {EXTENSION_ARCHIVO}: {zap}")
    destino = sesion.guardia.exigir_permitida(Path(carpeta_destino) / zap.stem)
    if destino.exists() and any(destino.iterdir()):
        raise EntradaInvalida(f"La carpeta destino no está vacía: {destino}")
    _exigir_sin_proyecto_principal(sesion)
    proyecto = sesion.tia.Projects.Retrieve(sesion.sis.FileInfo(str(zap)),
                                            sesion.sis.DirectoryInfo(str(destino)))
    sesion.usar_proyecto(proyecto)
    return f"Desarchivado en {ruta_proyecto(proyecto)}"


def guardar(sesion: SesionTia) -> str:
    sesion.proyecto.Save()
    return f"Proyecto guardado: {ruta_proyecto(sesion.proyecto)}"


def cerrar(sesion: SesionTia, guardar_cambios: bool = False) -> str:
    proyecto = sesion.proyecto
    ruta = ruta_proyecto(proyecto)
    if guardar_cambios:
        proyecto.Save()
    proyecto.Close()
    sesion.olvidar_proyecto()
    return f"Proyecto cerrado {'(guardado)' if guardar_cambios else '(sin guardar)'}: {ruta}"


def archivar(sesion: SesionTia, carpeta: str, nombre: str) -> str:
    _exigir_nombre_valido(nombre)
    destino = Path(carpeta).expanduser().absolute()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"{nombre}{EXTENSION_ARCHIVO}"
    if archivo.exists():
        raise EntradaInvalida(f"Ya existe {archivo}; usa otro nombre de versión.")
    for intento in range(1, _INTENTOS_ARCHIVAR + 1):
        try:
            sesion.proyecto.Archive(sesion.sis.DirectoryInfo(str(destino)), archivo.name,
                                    sesion.eng.ProjectArchivationMode.Compressed)
            return f"Proyecto archivado: {archivo}"
        except Exception as e:
            # TIA a veces sigue escribiendo tras guardar/compilar: se espera y se reintenta.
            if intento == _INTENTOS_ARCHIVAR:
                raise OperacionTiaFallida(f"TIA no pudo archivar: {detalle_error(e)}") from e
            time.sleep(_ESPERA_ENTRE_INTENTOS_S)
    return ""  # inalcanzable


def detalle_error(error: Exception) -> str:
    """Mensaje de una excepción .NET incluyendo las internas (TIA suele esconder ahí la causa real)."""
    partes, actual = [str(error).splitlines()[0] if str(error) else type(error).__name__], error
    while getattr(actual, "InnerException", None) is not None:
        actual = actual.InnerException
        partes.append(str(actual.Message))
    return " | ".join(partes)


def informacion(sesion: SesionTia) -> dict:
    proyecto = sesion.proyecto
    return {
        "nombre": str(proyecto.Name),
        "ruta": str(ruta_proyecto(proyecto)),
        "idioma_edicion": cultura_edicion(proyecto),
        "modificado": _atributo(proyecto, "IsModified"),
        "autor": _atributo(proyecto, "Author"),
    }


def cultura_edicion(proyecto) -> str:
    try:
        return str(proyecto.LanguageSettings.EditingLanguage.Culture.Name)
    except Exception:
        return "es-ES"


def _proyecto_abierto_en(sesion: SesionTia, archivo: Path):
    return next((p for p in sesion.tia.Projects
                 if ruta_proyecto(p).resolve() == archivo.resolve()), None)


def _exigir_sin_proyecto_principal(sesion: SesionTia) -> None:
    abiertos = [ruta_proyecto(p) for p in sesion.tia.Projects]
    if abiertos:
        raise ErrorTia(
            f"TIA ya tiene un proyecto abierto ({abiertos[0]}). Ciérralo antes con "
            f"`tia_proyecto` action='cerrar' (o ábrelo en solo lectura)."
        )


def _exigir_nombre_valido(nombre: str) -> None:
    if not _NOMBRE_VALIDO.match(nombre):
        raise EntradaInvalida(f"Nombre no válido '{nombre}': usa solo letras sin acentos, números, '_' o '-'.")


def _atributo(objeto, nombre: str):
    try:
        return str(objeto.GetAttribute(nombre))
    except Exception:
        return None
