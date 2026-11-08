"""Perfil de estilo de un proyecto: cómo nombra, estructura y documenta el equipo.

Se genera al "aprender" de un proyecto anterior y Claude lo lee antes de programar
para imitar las convenciones (prefijos, idioma, comentarios, instrucciones usadas).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ..simaticml.modelo import Acceso, BloqueLeido
from .arbol_llamadas import arbol_texto

_PREFIJO = re.compile(r"^([A-Za-z]{1,4})[_]")


def _prefijos(nombres: Iterable[str], minimo: int = 2) -> list[str]:
    nombres = list(nombres)
    conteo = Counter(m.group(1) + "_" for n in nombres if (m := _PREFIJO.match(n)))
    total = len(nombres) or 1
    return [f"{p} ({c * 100 // total} %)" for p, c in conteo.most_common(8) if c >= minimo]


def _estilo_nombre(nombre: str) -> str:
    if "_" in nombre:
        return "Snake_Case" if any(c.isupper() for c in nombre) else "snake_case"
    if nombre.isupper():
        return "MAYUSCULAS"
    return "PascalCase" if nombre[:1].isupper() else "camelCase"


def _porcentaje(parte: int, total: int) -> str:
    return f"{parte * 100 // total} %" if total else "-"


def perfil(nombre_proyecto: str, bloques: list[BloqueLeido], tags: list, ejemplos: int = 3) -> str:
    redes = [r for b in bloques for r in b.redes]
    # DB de instancia (repiten la interfaz de su FB) y OB (variables informativas de TIA) no son estilo propio
    miembros = [(seccion, m.nombre) for b in bloques if b.tipo not in ("InstanceDB", "OB")
                for seccion, ms in b.interfaz.items() for m in ms]
    instrucciones = Counter(u.instruccion for b in bloques for u in b.usos if u.acceso != Acceso.INSTANCIA)
    instancias = [u.operando for b in bloques for u in b.usos if u.acceso == Acceso.INSTANCIA]
    lenguajes = Counter(f"{b.tipo}/{b.lenguaje}" for b in bloques)
    estilos = Counter(_estilo_nombre(n) for n in [b.nombre for b in bloques] + [t.nombre for t in tags])

    lineas = [
        f"# Perfil de estilo: {nombre_proyecto}",
        "",
        "Generado automáticamente por TIA_MCP_V17. Úsalo como guía para programar igual que este proyecto.",
        "",
        "## Estructura",
        f"- Bloques: {len(bloques)} → " + ", ".join(f"{k}: {v}" for k, v in lenguajes.most_common()),
        f"- Redes: {len(redes)} | con título: {_porcentaje(sum(bool(r.titulo) for r in redes), len(redes))}"
        f" | con comentario: {_porcentaje(sum(bool(r.comentario) for r in redes), len(redes))}",
        f"- Instancias: {sum(i.startswith('#') for i in instancias)} multiinstancia (#) / "
        f"{sum(i.startswith(chr(34)) for i in instancias)} DB individual",
        "",
        "## Convenciones de nombres",
        f"- Estilo predominante: {', '.join(f'{k} ({v})' for k, v in estilos.most_common(3))}",
    ]
    for tipo in ("OB", "FB", "FC", "GlobalDB", "InstanceDB"):
        nombres = [b.nombre for b in bloques if b.tipo == tipo]
        if nombres:
            lineas.append(f"- {tipo}: prefijos {', '.join(_prefijos(nombres)) or 'sin prefijo fijo'}; "
                          f"ej.: {', '.join(nombres[:5])}")
    for seccion in ("Input", "Output", "InOut", "Static", "Temp"):
        nombres = [n for s, n in miembros if s == seccion]
        if nombres:
            lineas.append(f"- Interfaz {seccion}: prefijos {', '.join(_prefijos(nombres)) or 'sin prefijo fijo'}; "
                          f"ej.: {', '.join(nombres[:6])}")
    if tags:
        con_comentario = sum(bool(t.comentario) for t in tags)
        lineas += [f"- Tags: {len(tags)}, con comentario {_porcentaje(con_comentario, len(tags))}; prefijos "
                   f"{', '.join(_prefijos(t.nombre for t in tags)) or 'sin prefijo fijo'}",
                   f"  ej.: {', '.join(f'{t.nombre} {t.direccion}' for t in tags[:8])}"]
    lineas += ["", "## Instrucciones más usadas",
               "- " + ", ".join(f"{k} ({v})" for k, v in instrucciones.most_common(20)),
               "", "## Árbol de llamadas", "```", *arbol_texto(bloques)[:80], "```",
               "", "## Redes de ejemplo"]
    for b, r in _redes_representativas(bloques, ejemplos):
        lineas += [f"### {b.nombre} › Red {r.indice}: {r.titulo or '(sin título)'}",
                   *(f"> {r.comentario}",) * bool(r.comentario), "```", *r.sentencias, "```"]
    return "\n".join(lineas) + "\n"


def _redes_representativas(bloques: list[BloqueLeido], cantidad: int):
    candidatas = [(b, r) for b in bloques if b.lenguaje in ("LAD", "FBD") for r in b.redes
                  if r.sentencias and r.titulo]
    candidatas.sort(key=lambda br: -len(br[1].sentencias))
    return candidatas[:cantidad]
