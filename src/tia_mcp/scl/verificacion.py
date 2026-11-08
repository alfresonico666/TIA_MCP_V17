"""Verificación previa de código SCL antes de importarlo a TIA.

TIA informa muy mal los errores de importación de fuentes externas; aquí se
detectan antes los fallos más comunes: bloques sin cerrar, estructuras de
control desbalanceadas y caracteres no ASCII en identificadores.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_BLOQUES = ("FUNCTION_BLOCK", "FUNCTION", "ORGANIZATION_BLOCK", "DATA_BLOCK", "TYPE")
_ESTRUCTURAS = ("IF", "CASE", "FOR", "WHILE", "REPEAT", "REGION")
_COMENTARIOS = re.compile(r"//[^\n]*|\(\*.*?\*\)", re.DOTALL)
_CADENAS = re.compile(r"'(?:[^'$]|\$.)*'")


@dataclass
class ResultadoVerificacion:
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    bloques: list[str] = field(default_factory=list)

    @property
    def correcto(self) -> bool:
        return not self.errores

    def resumen(self) -> str:
        lineas = [f"Bloques detectados: {', '.join(self.bloques) or 'ninguno'}"]
        lineas += [f"  ERROR: {e}" for e in self.errores]
        lineas += [f"  AVISO: {a}" for a in self.advertencias]
        return "\n".join(lineas)


def verificar(codigo: str) -> ResultadoVerificacion:
    resultado = ResultadoVerificacion()
    limpio = _CADENAS.sub("''", _COMENTARIOS.sub(_conservar_saltos, codigo))
    palabras = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\"[^\"]*\"", limpio)
    mayus = [p.upper() for p in palabras]
    resultado.bloques = _nombres_de_bloques(limpio)
    if not resultado.bloques:
        resultado.errores.append("No hay ninguna declaración de bloque (FUNCTION_BLOCK, FUNCTION, DATA_BLOCK...).")
    for clave in (*_BLOQUES, *_ESTRUCTURAS):
        abiertos, cerrados = mayus.count(clave), mayus.count(f"END_{clave}")
        if abiertos != cerrados:
            resultado.errores.append(f"{clave}: {abiertos} abiertos y {cerrados} END_{clave}.")
    if any(b in mayus for b in ("FUNCTION_BLOCK", "FUNCTION", "ORGANIZATION_BLOCK")) and "BEGIN" not in mayus:
        resultado.errores.append("Falta BEGIN antes del código del bloque.")
    for numero, linea in enumerate(limpio.splitlines(), start=1):
        if any(ord(c) > 127 for c in linea):
            resultado.advertencias.append(f"Línea {numero}: caracteres no ASCII fuera de comentarios/textos "
                                          f"(acentos, ñ); TIA suele rechazarlos en identificadores.")
    return resultado


def _nombres_de_bloques(codigo: str) -> list[str]:
    patron = re.compile(r'^\s*(FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK|DATA_BLOCK|TYPE)\s+("[^"]+"|\w+)',
                        re.IGNORECASE | re.MULTILINE)
    return [f"{m.group(1).upper()} {m.group(2)}" for m in patron.finditer(codigo)]


def _conservar_saltos(m: re.Match) -> str:
    return "\n" * m.group(0).count("\n")
