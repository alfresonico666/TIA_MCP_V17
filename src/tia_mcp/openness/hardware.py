"""Dispositivos del proyecto y acceso al software de cada PLC."""
from __future__ import annotations

import difflib
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..errores import EntradaInvalida, NoEncontrado
from .cargador import implementacion
from .sesion import SesionTia


@dataclass
class Modulo:
    nombre: str
    referencia: str
    posicion: int | None
    ip: str | None = None


@dataclass
class Dispositivo:
    nombre: str
    tipo: str
    plc: str | None = None
    modulos: list[Modulo] = field(default_factory=list)


def dispositivos(sesion: SesionTia) -> list[Dispositivo]:
    return [_describir(sesion, d) for d in todos_los_dispositivos(sesion.proyecto)]


def agregar_plc(sesion: SesionTia, nombre: str, referencia: str) -> str:
    """referencia: '6ES7 214-1BG40-0XB0/V4.5' (referencia de catálogo/versión de firmware)."""
    if "/" not in referencia:
        raise EntradaInvalida("La referencia debe incluir el firmware, p. ej. '6ES7 214-1BG40-0XB0/V4.5'.")
    if any(p.Name == nombre for _, p in plcs(sesion)):
        raise EntradaInvalida(f"Ya existe un PLC llamado '{nombre}'.")
    sesion.proyecto.Devices.CreateWithItem(f"OrderNumber:{referencia}", nombre, nombre)
    return f"CPU {referencia} agregada como '{nombre}'."


def plcs(sesion: SesionTia) -> list[tuple[object, object]]:
    """[(dispositivo, PlcSoftware)] de todo el proyecto."""
    resultado = []
    for dispositivo in todos_los_dispositivos(sesion.proyecto):
        software = _software_plc(sesion, dispositivo)
        if software is not None:
            resultado.append((dispositivo, software))
    return resultado


def plc(sesion: SesionTia, nombre: str | None = None):
    """PlcSoftware por nombre del PLC o del dispositivo; si hay uno solo, el nombre es opcional."""
    encontrados = plcs(sesion)
    if not encontrados:
        raise NoEncontrado("ningún PLC en el proyecto", "", None)
    if nombre is None:
        if len(encontrados) > 1:
            nombres = [str(s.Name) for _, s in encontrados]
            raise EntradaInvalida(f"Hay varios PLC; indica `plc` (uno de: {', '.join(nombres)}).")
        return encontrados[0][1]
    for dispositivo, software in encontrados:
        if nombre in (str(software.Name), str(dispositivo.Name)):
            return software
    nombres = [str(s.Name) for _, s in encontrados]
    raise NoEncontrado("el PLC", nombre, difflib.get_close_matches(nombre, nombres))


# --------------------------------------------------------------------------- internos
def todos_los_dispositivos(proyecto) -> Iterator:
    vistos: set[str] = set()
    fuentes = (proyecto.Devices, _dispositivos_en_grupos(proyecto.DeviceGroups),
               proyecto.UngroupedDevicesGroup.Devices)
    for fuente in fuentes:
        for dispositivo in fuente:
            if str(dispositivo.Name) not in vistos:  # un dispositivo puede aparecer en dos colecciones
                vistos.add(str(dispositivo.Name))
                yield dispositivo


def _dispositivos_en_grupos(grupos) -> Iterator:
    for grupo in grupos:
        yield from grupo.Devices
        yield from _dispositivos_en_grupos(grupo.Groups)


def items_recursivos(items) -> Iterator:
    for item in items:
        yield item
        yield from items_recursivos(item.DeviceItems)


def _software_plc(sesion: SesionTia, dispositivo):
    for item in items_recursivos(dispositivo.DeviceItems):
        contenedor = item.GetService[sesion.eng.SoftwareContainer]()
        if contenedor is not None:
            software = implementacion(contenedor.Software)
            if isinstance(software, sesion.eng.PlcSoftware):
                return software
    return None


def _describir(sesion: SesionTia, dispositivo) -> Dispositivo:
    software = _software_plc(sesion, dispositivo)
    descripcion = Dispositivo(nombre=str(dispositivo.Name), tipo=str(dispositivo.TypeIdentifier or ""),
                              plc=str(software.Name) if software is not None else None)
    for item in items_recursivos(dispositivo.DeviceItems):
        referencia = str(item.TypeIdentifier or "")
        if not referencia.startswith("OrderNumber:"):
            continue
        descripcion.modulos.append(Modulo(nombre=str(item.Name),
                                          referencia=referencia.removeprefix("OrderNumber:"),
                                          posicion=_posicion(item), ip=_ip(sesion, item)))
    return descripcion


def _posicion(item) -> int | None:
    try:
        return int(item.PositionNumber)
    except Exception:
        return None


def _ip(sesion: SesionTia, item) -> str | None:
    for sub in items_recursivos(item.DeviceItems):
        interfaz = sub.GetService[sesion.eng.NetworkInterface]()
        if interfaz is None:
            continue
        for nodo in interfaz.Nodes:
            try:
                return str(nodo.GetAttribute("Address"))
            except Exception:
                continue
    return None
