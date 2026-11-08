"""Representación en texto de un bloque leído (lo que Claude "ve" de un bloque KOP/FUP/DB/UDT)."""
from __future__ import annotations

from .modelo import BloqueLeido, Miembro


def interfaz_como_texto(bloque: BloqueLeido) -> list[str]:
    lineas = []
    for seccion, miembros in bloque.interfaz.items():
        if miembros:
            lineas.append(f"  {seccion}:")
            lineas += _miembros(miembros, 2)
    return lineas


def _miembros(miembros: list[Miembro] | tuple[Miembro, ...], nivel: int) -> list[str]:
    lineas = []
    for m in miembros:
        inicial = f" := {m.valor_inicial}" if m.valor_inicial else ""
        comentario = f"  // {m.comentario}" if m.comentario else ""
        lineas.append(f"{'  ' * nivel}{m.nombre} : {m.tipo}{inicial}{comentario}")
        if m.hijos and not m.tipo.upper().startswith(("TON", "TOF", "TP", "CTU", "CTD", "R_TRIG", "F_TRIG")):
            lineas += _miembros(m.hijos, nivel + 1)
    return lineas


def bloque_como_texto(bloque: BloqueLeido, incluir_interfaz: bool = True) -> str:
    cabecera = f"{bloque.tipo} \"{bloque.nombre}\"" + (f" [{bloque.numero}]" if bloque.numero else "")
    cabecera += f" ({bloque.lenguaje})" + (f" — {bloque.titulo}" if bloque.titulo else "")
    lineas = [cabecera]
    if bloque.instancia_de:
        lineas.append(f"Instancia de: {bloque.instancia_de}")
    if bloque.comentario:
        lineas.append(f"// {bloque.comentario}")
    if incluir_interfaz and bloque.interfaz:
        lineas += ["Interfaz:", *interfaz_como_texto(bloque)]
    for red in bloque.redes:
        lineas.append(f"Red {red.indice}: {red.titulo or '(sin título)'}" + (f"  // {red.comentario}"
                                                                              if red.comentario else ""))
        lineas += [f"  {s}" for s in red.sentencias] or ["  (vacía)"]
    return "\n".join(lineas)
