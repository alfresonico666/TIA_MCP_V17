"""Contexto compartido por las herramientas MCP y utilidades de la capa de presentación."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..configuracion import Configuracion
from ..errores import EntradaInvalida, ErrorTia
from ..openness.hilo_tia import EjecutorTia
from ..openness.indice import IndicePrograma
from ..openness.programacion import Programador
from ..openness.sesion import SesionTia

log = logging.getLogger(__name__)

LECTURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
ESCRITURA = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


@dataclass
class Contexto:
    config: Configuracion
    sesion: SesionTia
    ejecutor: EjecutorTia
    indice: IndicePrograma
    programador: Programador
    solo_lectura: bool = False

    async def ejecutar(self, funcion: Callable[[], object]) -> str:
        """Ejecuta `funcion` en el hilo de TIA y traduce cualquier fallo a un error legible para Claude."""
        try:
            resultado = await self.ejecutor.ejecutar(funcion)
        except ErrorTia as e:
            raise ToolError(str(e)) from e
        except TimeoutError as e:
            raise ToolError(str(e)) from e
        except Exception as e:
            log.exception("Fallo inesperado")
            raise ToolError(f"Error de TIA/Openness ({type(e).__name__}): {e}") from e
        return como_texto(resultado)

    def exigir_escritura(self) -> None:
        if self.solo_lectura:
            raise EntradaInvalida("El servidor está en modo SOLO LECTURA (TIA_MCP_SOLO_LECTURA=1).")


def como_texto(resultado: object) -> str:
    if resultado is None:
        return "OK"
    if isinstance(resultado, str):
        return resultado
    if isinstance(resultado, Iterable):
        return "\n".join(str(r) for r in resultado)
    return str(resultado)


def requerido(valor, nombre: str, accion: str):
    if valor is None or valor == "":
        raise EntradaInvalida(f"action='{accion}' necesita el parámetro `{nombre}`.")
    return valor


def accion_desconocida(accion: str, validas: Iterable[str]) -> EntradaInvalida:
    return EntradaInvalida(f"action='{accion}' no existe. Válidas: {', '.join(validas)}.")
