"""Operandos KOP escritos como en TIA → nodos <Access> de SimaticML.

    #Marcha            variable local (interfaz del bloque)
    #T1.Q              miembro de una multiinstancia
    "Motor"  / Motor   variable global (tabla de variables)
    "DB_Datos".Nivel   miembro de un DB global
    T#5s  16#FF        constante con tipo (TypedConstant)
    10  2.5  TRUE      constante literal (Int / Real / Bool)
    %I0.0  %MW10       dirección absoluta (mejor usar la tabla de variables)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from ...errores import EntradaInvalida

_ENTERO = re.compile(r"^[+-]?\d+$")
_REAL = re.compile(r"^[+-]?\d+\.\d+([eE][+-]?\d+)?$")
_IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ABSOLUTA = re.compile(r"^%(?P<area>I|Q|M)(?P<ancho>[BWD]?)(?P<byte>\d+)(\.(?P<bit>[0-7]))?$", re.IGNORECASE)
_INDICE = re.compile(r"^(?P<nombre>[^\[\]]+)\[(?P<indice>[^\[\]]+)\]$")
_AREAS = {"I": "Input", "Q": "Output", "M": "Memory"}
_ANCHOS = {"": "Bool", "B": "Byte", "W": "Word", "D": "DWord"}
_INT_MAXIMO = 32767


@dataclass(frozen=True)
class Operando:
    alcance: str                       # GlobalVariable | LocalVariable | LiteralConstant | TypedConstant | Address
    componentes: tuple[str, ...] = ()
    valor: str = ""
    tipo: str = ""

    @property
    def es_constante(self) -> bool:
        return self.alcance in ("LiteralConstant", "TypedConstant")

    def xml(self, uid: int) -> str:
        if self.es_constante:
            tipo = f"<ConstantType>{escape(self.tipo)}</ConstantType>" if self.tipo else ""
            return (f'<Access Scope="{self.alcance}" UId="{uid}"><Constant>{tipo}'
                    f"<ConstantValue>{escape(self.valor)}</ConstantValue></Constant></Access>")
        if self.alcance == "Address":
            return f'<Access Scope="Address" UId="{uid}">{self.valor}</Access>'
        return (f'<Access Scope="{self.alcance}" UId="{uid}"><Symbol>'
                + "".join(_componente_xml(c) for c in self.componentes) + "</Symbol></Access>")

    def xml_instancia(self, uid: int) -> str:
        """<Instance> lleva los <Component> directamente (sin <Symbol>)."""
        return (f'<Instance Scope="{self.alcance}" UId="{uid}">'
                + "".join(_componente_xml(c) for c in self.componentes) + "</Instance>")


def operando(texto: str, tipo_sugerido: str | None = None) -> Operando:
    t = str(texto).strip()
    if not t:
        raise EntradaInvalida("Operando vacío.")
    if t.startswith("#"):
        return Operando("LocalVariable", _componentes(t[1:]))
    if t.startswith('"'):
        return Operando("GlobalVariable", _componentes(t))
    if t.startswith("%"):
        return _absoluta(t)
    if t.upper() in ("TRUE", "FALSE"):
        return Operando("LiteralConstant", valor=t.upper(), tipo="Bool")
    if "#" in t:
        return Operando("TypedConstant", valor=t)
    if _ENTERO.match(t):
        tipo = tipo_sugerido or ("Int" if abs(int(t)) <= _INT_MAXIMO else "DInt")
        return Operando("LiteralConstant", valor=t, tipo=tipo)
    if _REAL.match(t):
        return Operando("LiteralConstant", valor=t, tipo=tipo_sugerido or "Real")
    if _IDENTIFICADOR.match(t):
        return Operando("GlobalVariable", tuple(t.split(".")))
    raise EntradaInvalida(f"No entiendo el operando '{t}'. Usa #local, \"Global\", \"DB\".campo, "
                          f"T#5s, 10, 2.5 o TRUE.")


def instancia(texto: str) -> Operando:
    """Instancia de un temporizador/contador/FB: #Multiinstancia o "DB_Instancia"."""
    resultado = operando(texto)
    if resultado.alcance not in ("LocalVariable", "GlobalVariable"):
        raise EntradaInvalida(f"La instancia debe ser #Multiinstancia o \"DB\": '{texto}'.")
    return resultado


def _componentes(texto: str) -> tuple[str, ...]:
    partes, actual, entre_comillas, nivel = [], "", False, 0
    for c in texto:
        if c == '"':
            entre_comillas = not entre_comillas
            continue
        if c in "[]" and not entre_comillas:
            nivel += 1 if c == "[" else -1
        if c == "." and not entre_comillas and nivel == 0:
            partes.append(actual)
            actual = ""
            continue
        actual += c
    partes.append(actual)
    if any(not p for p in partes):
        raise EntradaInvalida(f"Operando mal formado: '{texto}'.")
    return tuple(partes)


def _componente_xml(componente: str) -> str:
    if _INDICE.match(componente):
        raise EntradaInvalida(f"Índices de array ('{componente}') no están soportados en KOP generado; "
                              f"usa SCL para esa lógica.")
    return f"<Component Name={quoteattr(componente)} />"


def _absoluta(texto: str) -> Operando:
    m = _ABSOLUTA.match(texto)
    if not m:
        raise EntradaInvalida(f"Dirección absoluta no soportada: '{texto}' (ej. %I0.0, %MW10).")
    ancho = m.group("ancho").upper()
    if (ancho == "") != (m.group("bit") is not None):
        raise EntradaInvalida(f"Dirección mal formada: '{texto}'.")
    desplazamiento = int(m.group("byte")) * 8 + int(m.group("bit") or 0)
    nodo = (f'<Address Area="{_AREAS[m.group("area").upper()]}" Type="{_ANCHOS[ancho]}" '
            f'BitOffset="{desplazamiento}" />')
    return Operando("Address", valor=nodo)
