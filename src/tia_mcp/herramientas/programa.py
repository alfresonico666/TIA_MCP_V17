"""Herramientas de programa: `tia_bloques` (leer), `tia_programar` (escribir), `tia_udt`, `tia_compilar`."""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..openness import bloques, conocimiento, hardware, tipos
from ..openness.compilacion import compilar
from ..simaticml.kop.instrucciones import resumen_catalogo
from ..simaticml.lector import leer_bloque
from ..simaticml.texto import bloque_como_texto
from .contexto import ESCRITURA, LECTURA, Contexto, accion_desconocida, requerido

AYUDA_KOP = """Especificación JSON de crear_kop:
{"tipo": "FB|FC|OB", "nombre": "FB_Motor", "numero": 10 (opcional), "titulo": "", "comentario": "",
 "tipo_ob": "ProgramCycle|CyclicInterrupt|Startup" (solo OB),
 "interfaz": {"Input": [{"nombre": "Marcha", "tipo": "Bool", "comentario": ""}],
              "Static": [{"nombre": "T_Arranque", "tipo": "TON_TIME"}, {"nombre": "Datos", "tipo": "\\"UDT_Motor\\""}]},
 "redes": [{"titulo": "", "comentario": "", "logica": NODO}]}
NODO (lista = serie):
 {"contacto": "#Marcha"} {"contacto": "#Paro", "negado": true} {"flanco": "P", "operando": "#S", "memoria": "#S_Mem"}
 {"bobina": "#Motor"} {"set": "#X"} {"reset": "#X"} {"comparar": ["#Nivel", ">", "50"], "tipo": "Int"}
 {"caja": "TON", "instancia": "#T_Arranque", "entradas": {"PT": "T#5s"}, "salidas": {"ET": "#Tiempo"}}
 {"llamar": "FB_Motor", "instancia": "DB_Motor1", "parametros": {"Marcha": "\\"Marcha\\""}}  (tipos leídos de TIA)
 {"serie": [...]} {"paralelo": [NODO, NODO]}
Operandos: #local, "Global", "DB".campo, #Inst.Q, T#5s, 10, 2.5, TRUE, %I0.0 (mejor simbólico)."""


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    @servidor.tool(annotations=LECTURA)
    async def tia_bloques(action: Literal["listar", "leer", "xml", "fuente", "exportar_todo"],
                          plc: str | None = None, nombre: str | None = None, filtro: str | None = None,
                          carpeta: str | None = None, limite: int = formato.LIMITE_POR_DEFECTO) -> str:
        """Leer el programa del PLC (`plc` opcional si hay uno solo).

        - listar: bloques con tipo, número, lenguaje, consistencia y carpeta (`filtro` por texto).
        - leer: `nombre` → KOP/FUP como lógica en texto + interfaz; SCL/STL/DB como fuente.
        - xml: SimaticML crudo del bloque `nombre` (para copiar formato o editar a mano).
        - fuente: fuente SCL/STL/DB generada por TIA.
        - exportar_todo: XML + .scl + .txt + UDT + tags a `carpeta` (para versionar en Git) y perfil de estilo.
        """
        def ejecutar():
            s = ctx.sesion
            sw = hardware.plc(s, plc)
            if action == "listar":
                filas = [formato.fila(b.nombre, tipo=b.tipo, n=b.numero, lenguaje=b.lenguaje, carpeta=b.carpeta,
                                      instancia_de=b.instancia_de, inconsistente="sí" if not b.consistente else None)
                         for b in bloques.listar(sw)]
                return formato.lineas("Bloques", formato.filtrar(filas, filtro), limite)
            if action == "exportar_todo":
                destino = requerido(carpeta, "carpeta", action)
                return conocimiento.exportar_programa(s, destino)
            bloque = bloques.buscar(sw, requerido(nombre, "nombre", action))
            if action == "xml":
                return bloques.xml_de(s, bloque)
            if action == "fuente":
                return bloques.fuente_de(s, sw, bloque)
            if action == "leer":
                if str(bloque.ProgrammingLanguage) in ("SCL", "STL"):
                    return bloques.fuente_de(s, sw, bloque)
                return bloque_como_texto(leer_bloque(bloques.xml_de(s, bloque)))
            raise accion_desconocida(action, ["listar", "leer", "xml", "fuente", "exportar_todo"])
        return await ctx.ejecutar(ejecutar)

    @servidor.tool(annotations=ESCRITURA)
    async def tia_programar(action: Literal["crear_kop", "importar_scl", "importar_xml", "crear_db_instancia",
                                            "borrar_bloque", "ayuda_kop"],
                            plc: str | None = None, especificacion: dict[str, Any] | None = None,
                            codigo: str | None = None, xml: str | None = None, carpeta: str | None = None,
                            nombre: str | None = None, fb: str | None = None, numero: int | None = None,
                            compilar_despues: bool = True, restaurar_si_falla: bool = True) -> str:
        """Escribir programa. Cada escritura valida, respalda el bloque si existía, importa y COMPILA;
        si no compila y el bloque existía, lo restaura. Devuelve los errores para corregirlos.

        - ayuda_kop: formato JSON de los bloques KOP y catálogo de instrucciones (TON, CTU, MOVE, PID...).
        - crear_kop: `especificacion` JSON (FB/FC/OB en KOP). Usa action='ayuda_kop' la primera vez.
        - importar_scl: `codigo` SCL con uno o varios FUNCTION_BLOCK/FUNCTION/DATA_BLOCK/TYPE.
          Ideal para PID, cálculos, máquinas de estado y UDT.
        - importar_xml: `xml` SimaticML completo.
        - crear_db_instancia: `nombre` del DB + `fb` [+ `numero`].
        - borrar_bloque: `nombre`.
        `carpeta` = carpeta de bloques destino ('Motores/Bombas'), se crea si no existe.
        """
        def ejecutar():
            if action == "ayuda_kop":
                return "\n".join([AYUDA_KOP, "", "Catálogo de cajas KOP:", *resumen_catalogo()])
            ctx.exigir_escritura()
            sw = hardware.plc(ctx.sesion, plc)
            p = ctx.programador
            if action == "crear_kop":
                return p.crear_kop(sw, requerido(especificacion, "especificacion", action), carpeta,
                                   compilar_despues, restaurar_si_falla)
            if action == "importar_scl":
                return p.importar_scl(sw, requerido(codigo, "codigo", action), carpeta, compilar_despues,
                                      restaurar_si_falla)
            if action == "importar_xml":
                return p.importar_xml(sw, requerido(xml, "xml", action), carpeta, compilar_despues,
                                      restaurar_si_falla)
            if action == "crear_db_instancia":
                return bloques.crear_db_instancia(sw, requerido(nombre, "nombre", action),
                                                  requerido(fb, "fb", action), numero)
            if action == "borrar_bloque":
                return bloques.borrar(bloques.buscar(sw, requerido(nombre, "nombre", action)))
            raise accion_desconocida(action, ["crear_kop", "importar_scl", "importar_xml", "crear_db_instancia",
                                              "borrar_bloque", "ayuda_kop"])
        return await ctx.ejecutar(ejecutar)

    @servidor.tool(annotations=ESCRITURA)
    async def tia_udt(action: Literal["listar", "leer", "crear", "borrar"], plc: str | None = None,
                      nombre: str | None = None, codigo: str | None = None) -> str:
        """Tipos de datos de usuario (UDT / PLC data types).

        - listar | leer: `nombre` → estructura con tipos, valores iniciales y comentarios.
        - crear: `codigo` SCL, p. ej. TYPE "UDT_Motor" VERSION : 0.1 STRUCT Marcha : Bool; ... END_STRUCT;
          END_TYPE (varios TYPE en un mismo código; también sirve para modificar uno existente).
        - borrar: `nombre`.
        Para usar un UDT en una interfaz o tag, escribe el tipo entre comillas: "UDT_Motor".
        """
        def ejecutar():
            sw = hardware.plc(ctx.sesion, plc)
            if action == "listar":
                return formato.lineas("UDT", [formato.fila(n, carpeta=c, inconsistente=None if ok else "sí")
                                              for n, c, ok in tipos.listar(sw)])
            if action == "leer":
                udt = tipos.buscar(sw, requerido(nombre, "nombre", action))
                return bloque_como_texto(leer_bloque(tipos.xml_de(ctx.sesion, udt)))
            ctx.exigir_escritura()
            if action == "crear":
                return ctx.programador.importar_scl(sw, requerido(codigo, "codigo", action))
            if action == "borrar":
                return tipos.borrar(sw, requerido(nombre, "nombre", action))
            raise accion_desconocida(action, ["listar", "leer", "crear", "borrar"])
        return await ctx.ejecutar(ejecutar)

    @servidor.tool(annotations=LECTURA)
    async def tia_compilar(action: Literal["software", "bloque"] = "software", plc: str | None = None,
                           nombre: str | None = None) -> str:
        """Compilar y obtener errores/advertencias con su ubicación (bloque › red).

        - software: todo el programa del PLC (la primera vez puede tardar 30-60 s).
        - bloque: solo `nombre`.
        """
        def ejecutar():
            sw = hardware.plc(ctx.sesion, plc)
            objetivo = bloques.buscar(sw, requerido(nombre, "nombre", action)) if action == "bloque" else sw
            return compilar(ctx.sesion, objetivo).resumen()
        return await ctx.ejecutar(ejecutar)
