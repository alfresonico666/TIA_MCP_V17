"""Herramientas `tia_sesion` y `tia_proyecto`."""
from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..openness import proyecto
from .contexto import ESCRITURA, Contexto, accion_desconocida, requerido


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=ESCRITURA)
    async def tia_sesion(action: Literal["estado", "conectar", "desconectar"], con_interfaz: bool = True,
                         pid: int | None = None) -> str:
        """Conexión con TIA Portal V17. EMPIEZA AQUÍ.

        - estado: procesos de TIA abiertos, conexión, proyecto activo y rutas permitidas.
        - conectar: se adjunta al TIA abierto (o al `pid` indicado); si no hay, inicia TIA
          (`con_interfaz`=false lo abre oculto, más rápido). La 1.ª vez TIA pide autorizar Openness:
          el usuario debe responder "Sí a todo" en TIA.
        - desconectar: suelta TIA (si lo inició el servidor, lo cierra).
        """
        def ejecutar():
            s = ctx.sesion
            if action == "conectar":
                return s.conectar(con_interfaz, pid)
            if action == "desconectar":
                return s.desconectar()
            if action == "estado":
                procesos = [formato.fila(f"PID {p.pid}", modo=p.modo, proyecto=p.proyecto) for p in s.procesos()]
                activo = str(proyecto.informacion(s)["ruta"]) if s.conectado and s.hay_proyecto else None
                return formato.secciones(
                    formato.lineas("Procesos de TIA Portal", procesos),
                    f"Conectado: {'sí' if s.conectado else 'no'} | proyecto activo: {activo or '-'}",
                    formato.lineas("Rutas permitidas (solo copias)", list(s.guardia.patrones)),
                    f"Modo: {'SOLO LECTURA' if ctx.solo_lectura else 'lectura y escritura'} | "
                    f"descarga a PLC: NO DISPONIBLE (por diseño)")
            raise accion_desconocida(action, ["estado", "conectar", "desconectar"])
        return await ctx.ejecutar(ejecutar)

    @servidor.tool(annotations=ESCRITURA)
    async def tia_proyecto(action: Literal["info", "abrir", "crear", "desarchivar", "guardar", "cerrar",
                                           "archivar"],
                           ruta: str | None = None, carpeta: str | None = None, nombre: str | None = None,
                           solo_lectura: bool = False, guardar_cambios: bool = False) -> str:
        """Proyecto TIA (solo COPIAS dentro de las rutas permitidas).

        - info: nombre, ruta, idioma de edición, si tiene cambios sin guardar.
        - abrir: `ruta` al .ap17 (`solo_lectura`=true para solo consultar).
        - crear: `carpeta` + `nombre` (sin acentos ni espacios).
        - desarchivar: `ruta` al .zap17 (puede estar en cualquier lado) → copia en `carpeta` permitida.
        - guardar | cerrar (`guardar_cambios`) | archivar: `carpeta` + `nombre` → crea <nombre>.zap17.
        """
        def ejecutar():
            s = ctx.sesion
            if action == "info":
                return "\n".join(f"{k}: {v}" for k, v in proyecto.informacion(s).items())
            if action == "abrir":
                return proyecto.abrir(s, requerido(ruta, "ruta", action), solo_lectura)
            if action == "crear":
                ctx.exigir_escritura()
                return proyecto.crear(s, requerido(carpeta, "carpeta", action), requerido(nombre, "nombre", action))
            if action == "desarchivar":
                return proyecto.desarchivar(s, requerido(ruta, "ruta", action), requerido(carpeta, "carpeta", action))
            if action == "guardar":
                ctx.exigir_escritura()
                return proyecto.guardar(s)
            if action == "cerrar":
                return proyecto.cerrar(s, guardar_cambios and not ctx.solo_lectura)
            if action == "archivar":
                return proyecto.archivar(s, requerido(carpeta, "carpeta", action), requerido(nombre, "nombre", action))
            raise accion_desconocida(action, ["info", "abrir", "crear", "desarchivar", "guardar", "cerrar", "archivar"])
        return await ctx.ejecutar(ejecutar)
