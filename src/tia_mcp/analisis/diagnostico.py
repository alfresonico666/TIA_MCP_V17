"""Reglas de diagnóstico sobre el programa leído: problemas típicos de lógica PLC.

Cada regla es una función pequeña que recibe el `Programa` y devuelve hallazgos.
Para agregar una regla nueva basta con escribirla y sumarla a `REGLAS`.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ..simaticml.modelo import Acceso, BloqueLeido
from .arbol_llamadas import instancias_compartidas, no_llamados
from .direcciones import solapamientos
from .referencias import nombre_base, operandos_usados


class Tag(Protocol):
    nombre: str
    direccion: str
    comentario: str


@dataclass(frozen=True)
class Hallazgo:
    gravedad: str          # error | advertencia | info
    regla: str
    mensaje: str

    def __str__(self) -> str:
        return f"[{self.gravedad.upper()}] {self.regla}: {self.mensaje}"


@dataclass
class Programa:
    bloques: list[BloqueLeido]
    tags: list[Tag] = field(default_factory=list)
    inconsistentes: list[str] = field(default_factory=list)
    instancias_sin_fb: list[str] = field(default_factory=list)


def _clave_global_o_local(bloque: BloqueLeido, operando: str) -> str:
    return operando if operando.startswith(('"', "%")) else f"{bloque.nombre}:{operando}"


def doble_bobina(p: Programa) -> list[Hallazgo]:
    escrituras: dict[str, list[str]] = defaultdict(list)
    for b in p.bloques:
        for u in b.usos:
            if u.acceso == Acceso.ESCRITURA and u.instruccion == "Coil":
                escrituras[_clave_global_o_local(b, u.operando)].append(f"{b.nombre} red {u.red}")
    return [Hallazgo("advertencia", "doble bobina",
                     f"{op} se asigna con bobina en {len(lugares)} lugares ({'; '.join(lugares)}); "
                     f"solo cuenta la última en el ciclo.")
            for op, lugares in escrituras.items() if len(lugares) > 1]


def set_sin_reset(p: Programa) -> list[Hallazgo]:
    sets, resets = set(), set()
    for b in p.bloques:
        for u in b.usos:
            if u.instruccion == "SCoil":
                sets.add(_clave_global_o_local(b, u.operando))
            elif u.instruccion == "RCoil":
                resets.add(_clave_global_o_local(b, u.operando))
    return ([Hallazgo("advertencia", "set sin reset", f"{op} se activa con S pero nunca se resetea con R.")
             for op in sorted(sets - resets)]
            + [Hallazgo("info", "reset sin set", f"{op} se resetea con R pero nunca se activa con S.")
               for op in sorted(resets - sets)])


def instancia_compartida(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("error", "instancia compartida",
                     f"{inst} la usan {len(lugares)} llamadas ({'; '.join(lugares)}); cada llamada necesita "
                     f"su propia instancia.")
            for inst, lugares in instancias_compartidas(p.bloques).items()]


def bloques_sin_llamar(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("advertencia", "bloque no llamado", f"{nombre} no se ejecuta desde ningún OB.")
            for nombre in no_llamados(p.bloques)]


def tags_sin_uso(p: Programa) -> list[Hallazgo]:
    usados = operandos_usados(p.bloques)
    sin_uso = [t.nombre for t in p.tags if t.nombre not in usados]
    if not sin_uso:
        return []
    return [Hallazgo("info", "tags sin uso", f"{len(sin_uso)} tags no se usan en el programa: "
                     f"{', '.join(sin_uso[:30])}{' ...' if len(sin_uso) > 30 else ''}")]


def marcas_leidas_sin_escribir(p: Programa) -> list[Hallazgo]:
    """Marcas/salidas que se leen pero nada las escribe (las entradas %I se excluyen: las escribe el hardware)."""
    direccion = {t.nombre: t.direccion for t in p.tags}
    leidos, escritos = set(), set()
    for b in p.bloques:
        for u in b.usos:
            if not u.operando.startswith('"'):
                continue
            (escritos if u.acceso == Acceso.ESCRITURA else leidos).add(nombre_base(u.operando))
    candidatos = sorted(n for n in leidos - escritos if direccion.get(n, "").upper().startswith(("%M", "%Q")))
    return [Hallazgo("advertencia", "leída sin escribir",
                     f"{n} ({direccion[n]}) se lee pero ningún bloque KOP/FUP la escribe (¿falta lógica o "
                     f"se escribe desde SCL/HMI?).") for n in candidatos]


def direcciones_solapadas(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("advertencia", "direcciones solapadas", f"{a} ({da}) y {b} ({db}) comparten bits.")
            for a, da, b, db in solapamientos([(t.nombre, t.direccion) for t in p.tags])]


def redes_vacias(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("info", "red vacía", f"{b.nombre} red {r.indice} no tiene lógica.")
            for b in p.bloques for r in b.redes if r.vacia and r.lenguaje in ("LAD", "FBD")]


def inconsistentes(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("error", "bloque inconsistente", f"{n} no compila; corrígelo antes de analizar.")
            for n in p.inconsistentes]


def instancias_huerfanas(p: Programa) -> list[Hallazgo]:
    return [Hallazgo("error", "DB de instancia huérfano", f"{n}: su FB no existe.") for n in p.instancias_sin_fb]


REGLAS: list[Callable[[Programa], list[Hallazgo]]] = [
    inconsistentes, instancias_huerfanas, instancia_compartida, doble_bobina, set_sin_reset,
    marcas_leidas_sin_escribir, direcciones_solapadas, bloques_sin_llamar, redes_vacias, tags_sin_uso,
]
_ORDEN = {"error": 0, "advertencia": 1, "info": 2}


def diagnosticar(programa: Programa) -> list[Hallazgo]:
    hallazgos = [h for regla in REGLAS for h in regla(programa)]
    return sorted(hallazgos, key=lambda h: _ORDEN[h.gravedad])
