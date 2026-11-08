"""Referencias cruzadas calculadas a partir de los bloques leídos (V17 no trae API de CrossReference)."""
from __future__ import annotations

from dataclasses import dataclass

from ..simaticml.modelo import Acceso, BloqueLeido


@dataclass(frozen=True)
class Referencia:
    bloque: str
    red: int
    acceso: Acceso
    instruccion: str
    operando: str


def normalizar(operando: str) -> str:
    """'Motor' y '"Motor"' son lo mismo; los locales (#x) y las direcciones (%I0.0) se dejan igual."""
    t = operando.strip()
    if not t or t[0] in '#"%':
        return t
    primero, _, resto = t.partition(".")
    return f'"{primero}"' + (f".{resto}" if resto else "")


def nombre_base(operando: str) -> str:
    """Primer componente sin comillas: '"DB_X".a.b' -> 'DB_X'; '#T1.Q' -> 'T1'."""
    t = operando.strip().lstrip("#")
    if t.startswith('"'):
        return t[1:].split('"', 1)[0]
    return t.split(".", 1)[0]


def coincide(usado: str, buscado: str) -> bool:
    """Coincidencia exacta o de miembro: buscar "DB_X" encuentra "DB_X".nivel."""
    return usado == buscado or usado.startswith(buscado + ".")


def referencias(bloques: list[BloqueLeido], operando: str, bloque: str | None = None) -> list[Referencia]:
    buscado = normalizar(operando)
    resultado = []
    for b in bloques:
        if bloque and b.nombre != bloque:
            continue
        resultado += [Referencia(b.nombre, u.red, u.acceso, u.instruccion, u.operando)
                      for u in b.usos if coincide(u.operando, buscado)]
    return sorted(resultado, key=lambda r: (r.bloque, r.red, r.acceso.value))


def operandos_usados(bloques: list[BloqueLeido]) -> set[str]:
    """Nombres base de todos los operandos globales usados (para detectar tags sin uso)."""
    return {nombre_base(u.operando) for b in bloques for u in b.usos if u.operando.startswith('"')}
