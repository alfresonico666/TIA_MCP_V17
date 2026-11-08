"""Convierte la especificación JSON que envía Claude en elementos KOP.

Bloque:
  {"tipo": "FB", "nombre": "FB_Motor", "numero": 10, "titulo": "...", "comentario": "...",
   "interfaz": {"Input": [{"nombre": "Marcha", "tipo": "Bool", "comentario": "..."}],
                "Static": [{"nombre": "T_Arranque", "tipo": "TON_TIME"}]},
   "redes": [{"titulo": "...", "comentario": "...", "logica": NODO}]}

NODO (una lista equivale a "serie"):
  {"contacto": "#Marcha"}                    {"contacto": "#Paro", "negado": true}
  {"flanco": "P", "operando": "#Pulsador", "memoria": "#Pulsador_Flanco"}
  {"bobina": "#Motor"}   {"set": "#Falla"}   {"reset": "#Falla"}
  {"comparar": ["#Nivel", ">", "50"], "tipo": "Int"}
  {"caja": "TON", "instancia": "#T_Arranque", "entradas": {"PT": "T#5s"}, "salidas": {"ET": "#Tiempo"}}
  {"llamar": "FB_Motor", "instancia": "DB_Motor1", "parametros": {"Marcha": "\"Marcha\""}}
  {"serie": [NODO, ...]}   {"paralelo": [NODO, NODO, ...]}
"""
from __future__ import annotations

from collections.abc import Callable

from ...errores import EntradaInvalida
from .elementos import (
    Bobina,
    Caja,
    Comparacion,
    Contacto,
    ContactoFlanco,
    DefinicionBloque,
    LlamadaBloque,
    Paralelo,
    Parametro,
    Red,
    Serie,
    Variable,
)

# bloque llamado -> {parámetro: (sección, tipo)}; lo provee el servicio leyendo TIA
InterfazDe = Callable[[str], dict[str, tuple[str, str]]]


def bloque_desde_json(datos: dict, interfaz_de: InterfazDe | None = None) -> DefinicionBloque:
    try:
        return DefinicionBloque(
            tipo=str(datos["tipo"]).upper(),
            nombre=datos["nombre"],
            numero=int(datos["numero"]),
            titulo=datos.get("titulo", ""),
            comentario=datos.get("comentario", ""),
            tipo_ob=datos.get("tipo_ob", "ProgramCycle"),
            interfaz={seccion: [_variable(v) for v in variables]
                      for seccion, variables in datos.get("interfaz", {}).items()},
            redes=[_red(r, interfaz_de) for r in datos["redes"]],
        )
    except KeyError as e:
        raise EntradaInvalida(f"Falta el campo obligatorio {e} en la especificación del bloque.") from e


def _variable(datos: dict) -> Variable:
    return Variable(nombre=datos["nombre"], tipo=datos.get("tipo", "Bool"), comentario=datos.get("comentario", ""),
                    valor_inicial=str(datos.get("valor_inicial", "")), version=datos.get("version"))


def _red(datos: dict, interfaz_de: InterfazDe | None) -> Red:
    return Red(titulo=datos.get("titulo", ""), comentario=datos.get("comentario", ""),
               logica=nodo(datos["logica"], interfaz_de))


def nodo(datos, interfaz_de: InterfazDe | None = None):
    if isinstance(datos, list):
        return Serie(*(nodo(d, interfaz_de) for d in datos))
    if not isinstance(datos, dict):
        raise EntradaInvalida(f"Nodo KOP no válido: {datos!r}")
    if "serie" in datos:
        return Serie(*(nodo(d, interfaz_de) for d in datos["serie"]))
    if "paralelo" in datos:
        return Paralelo(*(nodo(d, interfaz_de) for d in datos["paralelo"]))
    if "contacto" in datos:
        return Contacto(datos["contacto"], bool(datos.get("negado", False)))
    if "flanco" in datos:
        return ContactoFlanco(datos["operando"], datos["memoria"], str(datos["flanco"]).upper())
    for clave, tipo in (("bobina", "Coil"), ("set", "SCoil"), ("reset", "RCoil")):
        if clave in datos:
            return Bobina(datos[clave], tipo)
    if "comparar" in datos:
        a, operador, b = datos["comparar"]
        return Comparacion(a, operador, b, datos.get("tipo", "Int"))
    if "caja" in datos:
        return Caja(datos["caja"], datos.get("instancia"), dict(datos.get("entradas", {})),
                    dict(datos.get("salidas", {})), dict(datos.get("plantillas", {})), datos.get("version"))
    if "llamar" in datos:
        return _llamada(datos, interfaz_de)
    raise EntradaInvalida(f"Nodo KOP no reconocido (claves: {', '.join(datos)}). Ver la ayuda de crear_kop.")


def _llamada(datos: dict, interfaz_de: InterfazDe | None) -> LlamadaBloque:
    bloque = datos["llamar"]
    tipo = str(datos.get("tipo", "FB" if datos.get("instancia") else "FC")).upper()
    interfaz = interfaz_de(bloque) if interfaz_de else {}
    parametros = {}
    for nombre, valor in datos.get("parametros", {}).items():
        explicito = valor if isinstance(valor, dict) else {"op": valor}
        seccion, tipo_dato = interfaz.get(nombre, (explicito.get("seccion"), explicito.get("tipo")))
        if not seccion or not tipo_dato:
            raise EntradaInvalida(f"No conozco la sección/tipo del parámetro '{nombre}' de {bloque}. "
                                  f"¿Existe el bloque? Si no, indícalo: {{\"op\": ..., \"seccion\": \"Input\", "
                                  f"\"tipo\": \"Bool\"}}.")
        parametros[nombre] = Parametro(seccion, tipo_dato, explicito["op"])
    return LlamadaBloque(bloque, tipo, datos.get("instancia"), parametros)
