"""Construcción del servidor MCP: configuración, sesión con TIA y registro de herramientas."""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import __version__
from .configuracion import Configuracion
from .herramientas import registrar_todas
from .herramientas.contexto import Contexto
from .openness.hilo_tia import EjecutorTia
from .openness.indice import IndicePrograma
from .openness.programacion import Programador
from .openness.sesion import SesionTia
from .seguridad import GuardiaRutas

INSTRUCCIONES = """Servidor para programar Siemens TIA Portal V17 (S7-1200/1500) mediante Openness.
Flujo: tia_sesion(conectar) → tia_proyecto(abrir/crear, solo COPIAS) → leer/programar → tia_compilar.
- Antes de programar en un proyecto nuevo, revisa tia_conocimiento(listar/perfil) para seguir el estilo del equipo.
- KOP: tia_programar(ayuda_kop) y luego crear_kop. SCL: importar_scl (PID, cálculos, UDT con TYPE).
- Toda escritura compila sola; si hay errores, corrígelos y vuelve a importar.
- Diagnóstico: tia_analisis(diagnostico/referencias/arbol). Red PROFINET: tia_red.
- No existe descarga al PLC ni conexión online: la descarga la hace el usuario desde TIA.
Responde al usuario en español."""


def crear_servidor(config: Configuracion | None = None) -> tuple[MCPServer, Contexto]:
    config = config or Configuracion.desde_entorno()
    sesion = SesionTia(config, GuardiaRutas(config.rutas_permitidas))
    ctx = Contexto(config=config, sesion=sesion, ejecutor=EjecutorTia(), indice=IndicePrograma(),
                   programador=Programador(sesion),
                   solo_lectura=os.environ.get("TIA_MCP_SOLO_LECTURA", "") == "1")
    servidor = MCPServer("tia-v17", instructions=INSTRUCCIONES, version=__version__)
    registrar_todas(servidor, ctx)
    return servidor, ctx
