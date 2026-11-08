"""Herramientas `tia_hardware` y `tia_red` (PROFINET: IP, nombres, subred, sistema IO, E/S)."""
from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..openness import hardware, red
from .contexto import ESCRITURA, LECTURA, Contexto, accion_desconocida, requerido


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=LECTURA)
    async def tia_hardware(action: Literal["dispositivos", "agregar_plc"], nombre: str | None = None,
                           referencia: str | None = None) -> str:
        """Dispositivos del proyecto.

        - dispositivos: cada equipo con sus módulos (referencia/firmware, posición, IP) y su PLC.
        - agregar_plc: `nombre` + `referencia` con firmware, p. ej. '6ES7 214-1BG40-0XB0/V4.5'
          (S7-1214C AC/DC/RLY).
        """
        def ejecutar():
            s = ctx.sesion
            if action == "dispositivos":
                lineas = []
                for d in hardware.dispositivos(s):
                    lineas.append(formato.fila(d.nombre, tipo=d.tipo, plc=d.plc))
                    lineas += [f"    {formato.fila(m.nombre, ref=m.referencia, slot=m.posicion, ip=m.ip)}"
                               for m in d.modulos]
                return formato.lineas("Dispositivos y módulos", lineas, limite=0)
            if action == "agregar_plc":
                ctx.exigir_escritura()
                return hardware.agregar_plc(s, requerido(nombre, "nombre", action),
                                            requerido(referencia, "referencia", action))
            raise accion_desconocida(action, ["dispositivos", "agregar_plc"])
        return await ctx.ejecutar(ejecutar)

    acciones_red = ["interfaces", "configurar", "subred", "asignar_plc", "agregar_dispositivo", "insertar_modulo",
                    "direcciones_io", "cambiar_direccion_io"]

    @servidor.tool(annotations=ESCRITURA)
    async def tia_red(action: Literal["interfaces", "configurar", "subred", "asignar_plc", "agregar_dispositivo",
                                      "insertar_modulo", "direcciones_io", "cambiar_direccion_io"],
                      dispositivo: str | None = None, ip: str | None = None, mascara: str | None = None,
                      nombre_profinet: str | None = None, subred: str = red.SUBRED_POR_DEFECTO,
                      plc_destino: str | None = None, identificador: str | None = None,
                      modulo: str | None = None, posicion: int | None = None, contenedor: str | None = None,
                      tipo_io: Literal["Input", "Output"] | None = None, inicio: int | None = None) -> str:
        """Red PROFINET/Ethernet del proyecto (configuración OFFLINE; no toca equipos reales).

        - interfaces: IP, máscara, nombre PROFINET, subred, sistema IO y rol de cada equipo.
        - configurar: `dispositivo` + `ip` / `mascara` / `nombre_profinet` (minúsculas, p. ej. 'servo-eje-x').
        - subred: conecta `dispositivo` a `subred` (la crea si no existe; por defecto PN/IE_1).
        - asignar_plc: conecta `dispositivo` (drive, lector DMC, ET 200...) al sistema IO de `plc_destino`.
        - agregar_dispositivo: `dispositivo` (nombre) + `identificador`: referencia de catálogo
          ('6SL3210-5FE10-4UF0/V1.0') o GSDML instalado ('GSD:GSDML-V2.35-...xml/DAP/DAP 1').
        - insertar_modulo: `dispositivo` + `identificador` + `modulo` (nombre) + `posicion` [+ `contenedor`]
          (p. ej. telegrama de un drive o módulo de una ET 200).
        - direcciones_io: rangos %I/%Q de cada módulo de `dispositivo`.
        - cambiar_direccion_io: `dispositivo` + `modulo` + `tipo_io` + `inicio` (byte).
        """
        def ejecutar():
            s = ctx.sesion
            if action == "interfaces":
                return formato.lineas("Interfaces de red", [
                    formato.fila(f"{i.dispositivo}/{i.interfaz}", ip=i.ip, mascara=i.mascara,
                                 profinet=i.nombre_profinet, subred=i.subred, sistema_io=i.sistema_io, rol=i.rol)
                    for i in red.interfaces(s)])
            if action == "direcciones_io":
                return formato.lineas(f"Direcciones E/S de {dispositivo}",
                                      [str(d) for d in red.direcciones_io(s, requerido(dispositivo, "dispositivo",
                                                                                         action))])
            ctx.exigir_escritura()
            disp = requerido(dispositivo, "dispositivo", action)
            if action == "configurar":
                return red.configurar_interfaz(s, disp, ip, mascara, nombre_profinet)
            if action == "subred":
                return red.conectar_subred(s, disp, subred)
            if action == "asignar_plc":
                return red.asignar_a_plc(s, disp, requerido(plc_destino, "plc_destino", action))
            if action == "agregar_dispositivo":
                return red.agregar_dispositivo(s, disp, requerido(identificador, "identificador", action))
            if action == "insertar_modulo":
                return red.insertar_modulo(s, disp, requerido(identificador, "identificador", action),
                                           requerido(modulo, "modulo", action),
                                           requerido(posicion, "posicion", action), contenedor)
            if action == "cambiar_direccion_io":
                return red.cambiar_direccion_io(s, disp, requerido(modulo, "modulo", action),
                                                requerido(tipo_io, "tipo_io", action),
                                                requerido(inicio, "inicio", action))
            raise accion_desconocida(action, acciones_red)
        return await ctx.ejecutar(ejecutar)
