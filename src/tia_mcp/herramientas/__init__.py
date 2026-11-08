"""Herramientas MCP agrupadas por área; cada módulo expone `registrar(servidor, ctx)`."""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import analisis, hardware_red, hmi, programa, sesion_proyecto, tecnologia, variables
from .contexto import Contexto

_MODULOS = (sesion_proyecto, hardware_red, programa, variables, tecnologia, analisis, hmi)


def registrar_todas(servidor: MCPServer, ctx: Contexto) -> None:
    for modulo in _MODULOS:
        modulo.registrar(servidor, ctx)
