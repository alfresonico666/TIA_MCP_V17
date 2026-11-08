"""Usos de operandos y llamadas en código SCL (fuente de texto generada por TIA).

Es un análisis léxico, no un compilador: suficiente para referencias cruzadas
(quién lee/escribe qué) y para el árbol de llamadas de programas en SCL.
"""
from __future__ import annotations

import re

from ..simaticml.modelo import Acceso, Llamada, Uso

_COMENTARIOS = re.compile(r"//[^\n]*|\(\*.*?\*\)|/\*.*?\*/", re.DOTALL)
_CADENAS = re.compile(r"'(?:[^'$]|\$.)*'")
_OPERANDO = r'(?:#\w+|"[^"]+")(?:\.(?:\w+|"[^"]+"))*(?:\[[^\]]*\])?'
_RE_OPERANDO = re.compile(_OPERANDO)
_ASIGNACION = re.compile(rf"^\s*({_OPERANDO})\s*:=")
_SALIDA_PARAMETRO = re.compile(rf"=>\s*({_OPERANDO})")
_LLAMADA = re.compile(r'(#\w+|"[^"]+")\s*\(')
_INICIO_CODIGO = re.compile(r"\bBEGIN\b", re.IGNORECASE)
_FIN_BLOQUE = re.compile(r"\bEND_(FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK)\b", re.IGNORECASE)


def analizar(fuente: str) -> tuple[list[Uso], list[Llamada]]:
    """Devuelve (usos, llamadas sin resolver). En las llamadas, `bloque` es el nombre tal como aparece
    ("DB_Motor", #Multi, "FC_X"); el índice del proyecto lo resuelve a FB/FC."""
    codigo = _solo_codigo(fuente)
    usos: list[Uso] = []
    llamadas: list[Llamada] = []
    for numero, sentencia in enumerate(_sentencias(codigo), start=1):
        escritos = set()
        asignacion = _ASIGNACION.match(sentencia)
        if asignacion:
            escritos.add(asignacion.group(1))
        escritos.update(m.group(1) for m in _SALIDA_PARAMETRO.finditer(sentencia))
        llamados = {m.group(1) for m in _LLAMADA.finditer(sentencia)}
        for nombre in llamados:
            llamadas.append(Llamada(bloque=nombre, tipo_bloque="?", instancia=None, red=numero))
        for m in _RE_OPERANDO.finditer(sentencia):
            operando = _sin_indice(m.group(0))
            if m.group(0) in llamados:
                continue
            acceso = Acceso.ESCRITURA if m.group(0) in escritos else Acceso.LECTURA
            usos.append(Uso(operando, acceso, "SCL", numero))
    return usos, llamadas


def _solo_codigo(fuente: str) -> str:
    limpio = _CADENAS.sub("''", _COMENTARIOS.sub("", fuente))
    inicio = _INICIO_CODIGO.search(limpio)
    if inicio is None:
        return ""
    fin = _FIN_BLOQUE.search(limpio, inicio.end())
    return limpio[inicio.end(): fin.start() if fin else len(limpio)]


def _sentencias(codigo: str) -> list[str]:
    """Separa por ';' de primer nivel (los ';' dentro de paréntesis no cortan)."""
    sentencias, actual, nivel = [], "", 0
    for c in codigo:
        nivel += (c == "(") - (c == ")")
        if c == ";" and nivel == 0:
            sentencias.append(actual)
            actual = ""
        else:
            actual += c
    if actual.strip():
        sentencias.append(actual)
    return [f for s in sentencias for f in _fragmentos(s) if f.strip()]


_PALABRAS_CONTROL = re.compile(r"\b(?:IF|THEN|ELSE|ELSIF|DO|END_IF|END_FOR|END_WHILE|END_CASE|REPEAT|UNTIL|"
                               r"WHILE|CASE|OF|REGION|END_REGION)\b", re.IGNORECASE)


def _fragmentos(sentencia: str) -> list[str]:
    """'IF #a THEN #b := 1' -> ['#a', '#b := 1']: la condición se lee y la asignación escribe."""
    return _PALABRAS_CONTROL.split(sentencia)


def _sin_indice(operando: str) -> str:
    return operando.split("[", 1)[0]
