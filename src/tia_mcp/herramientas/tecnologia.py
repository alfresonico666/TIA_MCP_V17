"""Herramienta `tia_tecnologia`: objetos tecnológicos (PID_Compact, PID_3Step, PID_Temp...)."""
from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..openness import hardware, tecnologia
from .contexto import ESCRITURA, Contexto, accion_desconocida, requerido


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=ESCRITURA)
    async def tia_tecnologia(action: Literal["tipos", "listar", "crear", "parametros", "escribir_parametro"],
                             plc: str | None = None, nombre: str | None = None, tipo: str | None = None,
                             version: str | None = None, filtro: str | None = None, parametro: str | None = None,
                             valor: str | float | bool | None = None) -> str:
        """Objetos tecnológicos (regulación PID).

        - tipos: tipos habituales en S7-1200 y para qué sirven.
        - listar | crear: `nombre` + `tipo` ('PID_Compact') + `version` (según firmware de la CPU, p. ej. '2.3').
        - parametros: `nombre` [+ `filtro`] → parámetros y valores (límites, escalado, ganancias...).
        - escribir_parametro: `nombre` + `parametro` + `valor` (muestra valor anterior → nuevo).
        Flujo PID típico: crear el objeto → OB de alarma cíclica (OB30) que llame a PID_Compact
        (en SCL con tia_programar/importar_scl o en KOP con la caja PID_COMPACT) → configurar parámetros.
        """
        def ejecutar():
            if action == "tipos":
                return [f"{t}: {d}" for t, d in tecnologia.TIPOS_HABITUALES_S7_1200.items()]
            sw = hardware.plc(ctx.sesion, plc)
            if action == "listar":
                return formato.lineas("Objetos tecnológicos", [formato.fila(n, tipo=t, db=db)
                                                               for n, t, db in tecnologia.listar(sw)])
            if action == "parametros":
                return formato.lineas(f"Parámetros de {nombre}", [
                    f"{p} = {v}" for p, v in tecnologia.parametros(sw, requerido(nombre, "nombre", action), filtro)])
            ctx.exigir_escritura()
            if action == "crear":
                return tecnologia.crear(ctx.sesion, sw, requerido(nombre, "nombre", action),
                                        requerido(tipo, "tipo", action), requerido(version, "version", action))
            if action == "escribir_parametro":
                return tecnologia.escribir_parametro(sw, requerido(nombre, "nombre", action),
                                                     requerido(parametro, "parametro", action),
                                                     requerido(valor, "valor", action))
            raise accion_desconocida(action, ["tipos", "listar", "crear", "parametros", "escribir_parametro"])
        return await ctx.ejecutar(ejecutar)
