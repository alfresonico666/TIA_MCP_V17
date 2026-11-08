"""Red PROFINET/Ethernet: interfaces, IP, nombre PROFINET, subredes, sistema IO y direcciones E/S.

Pensado para dar de alta y direccionar rápido equipos de la red: servoamplificadores
(SINAMICS V90/S210), lectores de código (DMC), periferia ET 200, variadores, etc.
Todo es configuración OFFLINE del proyecto: nada se escribe en los equipos reales.
"""
from __future__ import annotations

import difflib
import ipaddress
import re
from dataclasses import dataclass

from ..errores import EntradaInvalida, NoEncontrado, OperacionTiaFallida
from .hardware import items_recursivos, todos_los_dispositivos
from .sesion import SesionTia

SUBRED_POR_DEFECTO = "PN/IE_1"
_TIPO_SUBRED_ETHERNET = "System:Subnet.Ethernet"
_NOMBRE_PN = re.compile(r"^[a-z0-9]([a-z0-9\-.]{0,238}[a-z0-9])?$")


@dataclass(frozen=True)
class InterfazRed:
    dispositivo: str
    interfaz: str
    ip: str | None
    mascara: str | None
    nombre_profinet: str | None
    subred: str | None
    sistema_io: str | None
    rol: str            # controlador | dispositivo IO | -


@dataclass(frozen=True)
class DireccionIO:
    modulo: str
    tipo: str           # Input | Output
    inicio: int
    longitud: int

    def __str__(self) -> str:
        letra = "I" if self.tipo == "Input" else "Q"
        bytes_ = max(1, (self.longitud + 7) // 8)
        return f"{self.modulo}: %{letra}{self.inicio}..{self.inicio + bytes_ - 1} ({self.longitud} bits)"


# --------------------------------------------------------------------------- lectura
def interfaces(sesion: SesionTia) -> list[InterfazRed]:
    resultado = []
    for dispositivo in todos_los_dispositivos(sesion.proyecto):
        for item, interfaz in _interfaces_de(sesion, dispositivo):
            for nodo in interfaz.Nodes:
                resultado.append(InterfazRed(
                    dispositivo=str(dispositivo.Name), interfaz=str(item.Name),
                    ip=_atributo(nodo, "Address"), mascara=_atributo(nodo, "SubnetMask"),
                    nombre_profinet=_atributo(nodo, "PnDeviceName"),
                    subred=str(nodo.ConnectedSubnet.Name) if nodo.ConnectedSubnet is not None else None,
                    sistema_io=_sistema_io(interfaz), rol=_rol(interfaz)))
    return resultado


def direcciones_io(sesion: SesionTia, nombre_dispositivo: str) -> list[DireccionIO]:
    dispositivo = buscar_dispositivo(sesion, nombre_dispositivo)
    return [DireccionIO(str(item.Name), str(d.IoType), int(d.StartAddress), int(d.Length))
            for item in items_recursivos(dispositivo.DeviceItems) for d in item.Addresses
            if str(d.IoType) in ("Input", "Output")]


# --------------------------------------------------------------------------- escritura
def configurar_interfaz(sesion: SesionTia, nombre_dispositivo: str, ip: str | None = None,
                        mascara: str | None = None, nombre_profinet: str | None = None) -> list[str]:
    nodo = _primer_nodo(sesion, nombre_dispositivo)
    cambios = []
    if ip:
        _validar_ip(ip)
        cambios.append(_cambiar(nodo, "Address", ip))
    if mascara:
        _validar_ip(mascara)
        cambios.append(_cambiar(nodo, "SubnetMask", mascara))
    if nombre_profinet:
        if not _NOMBRE_PN.match(nombre_profinet):
            raise EntradaInvalida(f"Nombre PROFINET no válido '{nombre_profinet}': solo minúsculas, números, "
                                  f"'-' y '.', sin empezar ni terminar con '-'.")
        _poner(nodo, "PnDeviceNameAutoGeneration", False)
        cambios.append(_cambiar(nodo, "PnDeviceName", nombre_profinet))
    if not cambios:
        raise EntradaInvalida("Indica al menos ip, mascara o nombre_profinet.")
    return [f"{nombre_dispositivo}: {c}" for c in cambios]


def conectar_subred(sesion: SesionTia, nombre_dispositivo: str, subred: str = SUBRED_POR_DEFECTO) -> str:
    nodo = _primer_nodo(sesion, nombre_dispositivo)
    existente = sesion.proyecto.Subnets.Find(subred)
    if nodo.ConnectedSubnet is not None and str(nodo.ConnectedSubnet.Name) == subred:
        return f"{nombre_dispositivo} ya estaba en la subred {subred}."
    if existente is None:
        nodo.CreateAndConnectToSubnet(subred)
        return f"Subred {subred} creada y {nombre_dispositivo} conectado."
    nodo.ConnectToSubnet(existente)
    return f"{nombre_dispositivo} conectado a la subred {subred}."


def asignar_a_plc(sesion: SesionTia, nombre_dispositivo: str, nombre_plc: str) -> str:
    """Conecta un dispositivo IO (drive, lector DMC, ET 200...) al sistema PROFINET IO del PLC."""
    interfaz_plc = _interfaz_con(sesion, nombre_plc, lambda i: len(list(i.IoControllers)) > 0, "controlador IO")
    controlador = interfaz_plc.IoControllers[0]
    subred = interfaz_plc.Nodes[0].ConnectedSubnet
    if subred is None:
        conectar_subred(sesion, nombre_plc)
        subred = interfaz_plc.Nodes[0].ConnectedSubnet
    sistema = controlador.IoSystem or controlador.CreateIoSystem("PROFINET IO-System")
    interfaz_dev = _interfaz_con(sesion, nombre_dispositivo, lambda i: len(list(i.IoConnectors)) > 0,
                                 "conector IO (¿es un dispositivo PROFINET IO?)")
    nodo_dev = interfaz_dev.Nodes[0]
    if nodo_dev.ConnectedSubnet is None or str(nodo_dev.ConnectedSubnet.Name) != str(subred.Name):
        nodo_dev.ConnectToSubnet(subred)
    interfaz_dev.IoConnectors[0].ConnectToIoSystem(sistema)
    return f"{nombre_dispositivo} asignado a {nombre_plc} ({sistema.Name}, subred {subred.Name})."


def agregar_dispositivo(sesion: SesionTia, nombre: str, identificador: str) -> str:
    """identificador: 'OrderNumber:6SL3210-5FE10-4UF0/V1.0' (catálogo) o 'GSD:<archivo.xml>/DAP/<id>' (GSDML
    ya instalado en TIA)."""
    if not identificador.startswith(("OrderNumber:", "GSD:", "System:")):
        identificador = f"OrderNumber:{identificador}"
    if any(str(d.Name) == nombre for d in todos_los_dispositivos(sesion.proyecto)):
        raise EntradaInvalida(f"Ya existe un dispositivo llamado '{nombre}'.")
    try:
        sesion.proyecto.Devices.CreateWithItem(identificador, nombre, nombre)
    except Exception as e:
        raise OperacionTiaFallida(
            f"TIA no pudo crear '{identificador}': {e}. Verifica la referencia y versión en el catálogo, o que "
            f"el GSDML esté instalado (Opciones > Administrar archivos GSD)."
        ) from e
    return f"Dispositivo '{nombre}' agregado ({identificador})."


def insertar_modulo(sesion: SesionTia, nombre_dispositivo: str, identificador: str, nombre_modulo: str,
                    posicion: int, contenedor: str | None = None) -> str:
    """Enchufa un módulo/submódulo (p. ej. un telegrama de un drive GSD) en un slot del dispositivo."""
    dispositivo = buscar_dispositivo(sesion, nombre_dispositivo)
    destino = _item_por_nombre(dispositivo, contenedor) if contenedor else dispositivo.DeviceItems[0]
    if not destino.CanPlugNew(identificador, nombre_modulo, posicion):
        raise OperacionTiaFallida(f"No se puede insertar '{identificador}' en {destino.Name} posición {posicion}.")
    destino.PlugNew(identificador, nombre_modulo, posicion)
    return f"Módulo '{nombre_modulo}' insertado en {destino.Name} (posición {posicion})."


def cambiar_direccion_io(sesion: SesionTia, nombre_dispositivo: str, modulo: str, tipo: str, inicio: int) -> str:
    dispositivo = buscar_dispositivo(sesion, nombre_dispositivo)
    item = _item_por_nombre(dispositivo, modulo)
    direccion = next((d for d in item.Addresses if str(d.IoType) == tipo), None)
    if direccion is None:
        raise NoEncontrado(f"una dirección {tipo} en", modulo)
    anterior = int(direccion.StartAddress)
    direccion.StartAddress = inicio
    return f"{nombre_dispositivo}/{modulo} {tipo}: {anterior} -> {inicio}"


# --------------------------------------------------------------------------- internos
def buscar_dispositivo(sesion: SesionTia, nombre: str):
    todos = list(todos_los_dispositivos(sesion.proyecto))
    for dispositivo in todos:
        if str(dispositivo.Name) == nombre:
            return dispositivo
    nombres = [str(d.Name) for d in todos]
    raise NoEncontrado("el dispositivo", nombre, difflib.get_close_matches(nombre, nombres))


def _interfaces_de(sesion: SesionTia, dispositivo):
    for item in items_recursivos(dispositivo.DeviceItems):
        interfaz = item.GetService[sesion.eng.NetworkInterface]()
        if interfaz is not None and len(list(interfaz.Nodes)) > 0:
            yield item, interfaz


def _interfaz_con(sesion: SesionTia, nombre_dispositivo: str, condicion, que: str):
    dispositivo = buscar_dispositivo(sesion, nombre_dispositivo)
    for _, interfaz in _interfaces_de(sesion, dispositivo):
        if condicion(interfaz):
            return interfaz
    raise NoEncontrado(f"una interfaz con {que} en", nombre_dispositivo)


def _primer_nodo(sesion: SesionTia, nombre_dispositivo: str):
    dispositivo = buscar_dispositivo(sesion, nombre_dispositivo)
    for _, interfaz in _interfaces_de(sesion, dispositivo):
        return interfaz.Nodes[0]
    raise NoEncontrado("una interfaz de red en", nombre_dispositivo)


def _item_por_nombre(dispositivo, nombre: str):
    for item in items_recursivos(dispositivo.DeviceItems):
        if str(item.Name) == nombre:
            return item
    nombres = [str(i.Name) for i in items_recursivos(dispositivo.DeviceItems)]
    raise NoEncontrado(f"el módulo de {dispositivo.Name}", nombre, difflib.get_close_matches(nombre, nombres))


def _sistema_io(interfaz) -> str | None:
    for controlador in interfaz.IoControllers:
        if controlador.IoSystem is not None:
            return str(controlador.IoSystem.Name)
    for conector in interfaz.IoConnectors:
        if conector.ConnectedToIoSystem is not None:
            return str(conector.ConnectedToIoSystem.Name)
    return None


def _rol(interfaz) -> str:
    if list(interfaz.IoControllers):
        return "controlador"
    return "dispositivo IO" if list(interfaz.IoConnectors) else "-"


def _validar_ip(texto: str) -> None:
    try:
        ipaddress.IPv4Address(texto)
    except ValueError as e:
        raise EntradaInvalida(f"Dirección IPv4 no válida: {texto}") from e


def _atributo(objeto, nombre: str) -> str | None:
    try:
        valor = objeto.GetAttribute(nombre)
        return str(valor) if valor is not None else None
    except Exception:
        return None


def _poner(objeto, nombre: str, valor) -> None:
    try:
        objeto.SetAttribute(nombre, valor)
    except Exception as e:
        raise OperacionTiaFallida(f"No se pudo cambiar {nombre}: {e}") from e


def _cambiar(objeto, nombre: str, valor) -> str:
    anterior = _atributo(objeto, nombre)
    _poner(objeto, nombre, valor)
    return f"{nombre}: {anterior} -> {valor}"
