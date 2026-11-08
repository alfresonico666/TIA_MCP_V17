"""Herramientas `tia_analisis` (diagnóstico) y `tia_conocimiento` (aprender de proyectos anteriores)."""
from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..analisis import arbol_llamadas, diagnostico
from ..analisis.referencias import referencias
from ..openness import conocimiento, hardware
from .contexto import ESCRITURA, LECTURA, Contexto, accion_desconocida, requerido


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=LECTURA)
    async def tia_analisis(action: Literal["referencias", "llamadores", "arbol", "no_llamados", "diagnostico"],
                           plc: str | None = None, operando: str | None = None, bloque: str | None = None,
                           limite: int = formato.LIMITE_POR_DEFECTO) -> str:
        """Diagnóstico del programa (lee todos los bloques; KOP/FUP por XML y SCL por su fuente).

        - referencias: dónde se lee/escribe `operando` ("Motor", #Marcha, "DB_X".campo) [`bloque` filtra].
        - llamadores: quién llama a `bloque` y con qué instancia.
        - arbol: árbol de llamadas desde los OB (o desde `bloque`).
        - no_llamados: FB/FC que ningún OB ejecuta.
        - diagnostico: doble bobina, set sin reset, instancias compartidas, marcas leídas sin escribir,
          direcciones solapadas, bloques no llamados, inconsistentes, DB huérfanos, tags sin uso.
        """
        def ejecutar():
            sw = hardware.plc(ctx.sesion, plc)
            if action == "diagnostico":
                hallazgos = diagnostico.diagnosticar(ctx.indice.programa(ctx.sesion, sw))
                return formato.lineas("Diagnóstico", [str(h) for h in hallazgos], limite)
            leidos = ctx.indice.leer(ctx.sesion, sw).bloques
            if action == "referencias":
                refs = referencias(leidos, requerido(operando, "operando", action), bloque)
                return formato.lineas(f"Referencias de {operando}", [
                    f"{r.bloque} red {r.red}: {r.acceso.value:<9} {r.instruccion}  ({r.operando})" for r in refs],
                    limite)
            if action == "llamadores":
                nombre = requerido(bloque, "bloque", action)
                return formato.lineas(f"Llamadas a {nombre}", [
                    formato.fila(b, red=r, instancia=i) for b, r, i in arbol_llamadas.llamadores(leidos, nombre)])
            if action == "arbol":
                return "\n".join(arbol_llamadas.arbol_texto(leidos, bloque)) or "(sin OB)"
            if action == "no_llamados":
                return formato.lineas("FB/FC no llamados", arbol_llamadas.no_llamados(leidos))
            raise accion_desconocida(action, ["referencias", "llamadores", "arbol", "no_llamados", "diagnostico"])
        return await ctx.ejecutar(ejecutar)

    @servidor.tool(annotations=ESCRITURA)
    async def tia_conocimiento(action: Literal["aprender", "listar", "perfil"], ruta: str | None = None,
                               nombre: str | None = None, carpeta_desarchivado: str | None = None) -> str:
        """Aprender el estilo del equipo a partir de proyectos V17 anteriores (copias).

        - aprender: `ruta` a un .ap17 (en carpeta permitida) o .zap17 (se desarchiva en una copia). Se abre en
          solo lectura, se exporta todo y se genera PERFIL_ESTILO.md (prefijos, estructura, comentarios,
          instrucciones usadas, árbol de llamadas y redes de ejemplo). No se guarda nada en el proyecto.
        - listar: proyectos ya aprendidos.
        - perfil: `nombre` → PERFIL_ESTILO.md. LÉELO antes de programar para seguir las convenciones del equipo.
        """
        def ejecutar():
            if action == "aprender":
                return conocimiento.aprender(ctx.sesion, requerido(ruta, "ruta", action), carpeta_desarchivado)
            if action == "listar":
                return formato.lineas(f"Proyectos aprendidos (en {ctx.config.dir_conocimiento})",
                                      conocimiento.listar(ctx.sesion))
            if action == "perfil":
                return conocimiento.leer_perfil(ctx.sesion, requerido(nombre, "nombre", action))
            raise accion_desconocida(action, ["aprender", "listar", "perfil"])
        return await ctx.ejecutar(ejecutar)
