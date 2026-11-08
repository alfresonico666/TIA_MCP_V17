"""Herramienta `tia_tags`: tablas de variables, ocupación de direcciones y organización por categorías."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..analisis.direcciones import siguiente_libre, solapamientos
from ..analisis.organizar_tags import REGLAS_SUGERIDAS
from ..openness import hardware, tags
from .contexto import ESCRITURA, Contexto, accion_desconocida, requerido

_ACCIONES = ["tablas", "leer_tabla", "buscar", "crear", "borrar", "ocupacion", "siguiente_libre",
             "reglas_sugeridas", "organizar"]


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=ESCRITURA)
    async def tia_tags(action: Literal["tablas", "leer_tabla", "buscar", "crear", "borrar", "ocupacion",
                                       "siguiente_libre", "reglas_sugeridas", "organizar"],
                       plc: str | None = None, tabla: str | None = None, filtro: str | None = None,
                       nuevos: list[dict[str, Any]] | None = None, nombre: str | None = None,
                       area: Literal["I", "Q", "M"] | None = None, tipo: str = "Bool",
                       reglas: list[dict[str, Any]] | None = None, aplicar: bool = False,
                       limite: int = formato.LIMITE_POR_DEFECTO) -> str:
        """Variables PLC (tablas de tags).

        - tablas | leer_tabla (`tabla`) | buscar (`filtro` en nombre, dirección o comentario).
        - crear: `tabla` + `nuevos` = [{"nombre", "tipo", "direccion", "comentario"}] (crea o actualiza;
          si el tag existe en otra tabla se actualiza allí). Tipos UDT entre comillas: "\\"UDT_Motor\\"".
        - borrar: `nombre`.
        - ocupacion: direcciones usadas y SOLAPAMIENTOS entre tags.
        - siguiente_libre: `area` (I/Q/M) + `tipo` (Bool, Int, Real...) → próxima dirección libre.
        - reglas_sugeridas: reglas de categoría por defecto (LVDTs, finales de carrera, pulsadores...).
        - organizar: mueve los tags a tablas por categoría según `reglas` (o las sugeridas).
          Cada regla: {"tabla", "prefijos", "contiene", "comentario", "direcciones" ("%IW*"), "tipos", "todas"}.
          Gana la primera regla que coincide. Por defecto es SIMULACIÓN: muestra el plan;
          con `aplicar`=true lo ejecuta (`tabla` limita a los tags de esa tabla de origen).
        """
        def ejecutar():
            s = ctx.sesion
            sw = hardware.plc(s, plc)
            if action == "tablas":
                return formato.lineas("Tablas de variables", [
                    formato.fila(str(t.Name), carpeta=c, tags=len(list(t.Tags))) for t, c in tags.recorrer_tablas(sw)])
            if action in ("leer_tabla", "buscar"):
                lista = tags.de_tabla(s, sw, requerido(tabla, "tabla", action)) if action == "leer_tabla" \
                    else tags.todos(s, sw)
                filas = [formato.fila(t.nombre, tipo=t.tipo, dir=t.direccion, tabla=t.tabla, coment=t.comentario)
                         for t in lista]
                return formato.lineas("Tags", formato.filtrar(filas, filtro), limite)
            if action == "ocupacion":
                pares = [(t.nombre, t.direccion) for t in tags.todos(s, sw)]
                conflictos = [f"{a} {da}  <->  {b} {db}" for a, da, b, db in solapamientos(pares)]
                usadas = sorted(f"{d} {n}" for n, d in pares if d)
                return formato.secciones(formato.lineas("SOLAPAMIENTOS", conflictos),
                                         formato.lineas("Direcciones usadas", usadas, limite))
            if action == "siguiente_libre":
                pares = [(t.nombre, t.direccion) for t in tags.todos(s, sw)]
                return siguiente_libre(pares, requerido(area, "area", action), tipo)
            if action == "reglas_sugeridas":
                return [f"{r.tabla}: " + formato.clave_valor(prefijos=list(r.prefijos), comentario=list(r.comentario),
                                                              direcciones=list(r.direcciones))
                        for r in REGLAS_SUGERIDAS]
            if action == "organizar":
                if aplicar:
                    ctx.exigir_escritura()
                return tags.organizar(s, sw, reglas, aplicar, tabla)
            ctx.exigir_escritura()
            if action == "crear":
                return tags.crear_o_actualizar(s, sw, requerido(tabla, "tabla", action),
                                               requerido(nuevos, "nuevos", action))
            if action == "borrar":
                return tags.borrar(sw, requerido(nombre, "nombre", action))
            raise accion_desconocida(action, _ACCIONES)
        return await ctx.ejecutar(ejecutar)
