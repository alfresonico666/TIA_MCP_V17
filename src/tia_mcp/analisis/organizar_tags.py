"""Clasifica tags en tablas por categoría (LVDTs, finales de carrera, entradas, salidas...).

Las reglas se evalúan en orden y gana la primera que coincide. Dentro de una regla,
basta con que coincida UNO de sus criterios (prefijo, texto en el nombre, palabra en el
comentario, patrón de dirección o tipo), salvo que se pida `todas=True`.
Este módulo solo calcula el plan; aplicarlo (mover tags) lo hace `openness.tags`.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Protocol

from ..errores import EntradaInvalida


class Tag(Protocol):
    nombre: str
    tipo: str
    direccion: str
    comentario: str
    tabla: str


@dataclass(frozen=True)
class ReglaCategoria:
    tabla: str
    prefijos: tuple[str, ...] = ()
    contiene: tuple[str, ...] = ()
    comentario: tuple[str, ...] = ()
    direcciones: tuple[str, ...] = ()    # comodines: "%I*.*" (bits de entrada), "%IW*" (palabras de entrada)
    tipos: tuple[str, ...] = ()
    todas: bool = False

    def coincide(self, tag: Tag) -> bool:
        nombre, comentario = tag.nombre.lower(), (tag.comentario or "").lower()
        criterios = [
            (self.prefijos, lambda: any(nombre.startswith(p.lower()) for p in self.prefijos)),
            (self.contiene, lambda: any(c.lower() in nombre for c in self.contiene)),
            (self.comentario, lambda: any(c.lower() in comentario for c in self.comentario)),
            (self.direcciones, lambda: any(fnmatch(tag.direccion.upper(), d.upper()) for d in self.direcciones)),
            (self.tipos, lambda: any(tag.tipo.lower() == t.lower() for t in self.tipos)),
        ]
        evaluados = [prueba() for valores, prueba in criterios if valores]
        if not evaluados:
            return False
        return all(evaluados) if self.todas else any(evaluados)

    @classmethod
    def desde_dict(cls, datos: dict) -> ReglaCategoria:
        if not datos.get("tabla"):
            raise EntradaInvalida(f"Cada regla necesita 'tabla': {datos}")
        claves = ("prefijos", "contiene", "comentario", "direcciones", "tipos")
        desconocidas = set(datos) - {"tabla", "todas", *claves}
        if desconocidas:
            raise EntradaInvalida(f"Claves desconocidas en la regla: {sorted(desconocidas)}. Válidas: tabla, "
                                  f"{', '.join(claves)}, todas.")
        return cls(tabla=datos["tabla"], todas=bool(datos.get("todas", False)),
                   **{k: tuple(datos.get(k, ())) for k in claves})


@dataclass(frozen=True)
class Movimiento:
    tag: str
    direccion: str
    origen: str
    destino: str


# Reglas de partida (editables): de lo más específico a lo más general.
REGLAS_SUGERIDAS: tuple[ReglaCategoria, ...] = (
    ReglaCategoria("LVDTs", prefijos=("LVDT",), comentario=("lvdt", "desplazamiento lineal")),
    ReglaCategoria("Finales_de_carrera", prefijos=("FC_", "LS_", "FDC", "SQ"),
                   comentario=("final de carrera", "fin de carrera", "limit switch")),
    ReglaCategoria("Paros_de_emergencia", prefijos=("PE_", "ES_", "SETA"), comentario=("emergencia", "e-stop")),
    ReglaCategoria("Pulsadores_y_selectores", prefijos=("PB_", "SB", "SEL_", "SS_"),
                   comentario=("pulsador", "selector", "botón", "boton")),
    ReglaCategoria("Pilotos", prefijos=("HL", "PL_", "LAMP"), comentario=("piloto", "lámpara", "lampara", "baliza")),
    ReglaCategoria("Valvulas", prefijos=("YV", "EV_", "VAL"), comentario=("válvula", "valvula", "electroválvula")),
    ReglaCategoria("Motores", prefijos=("KM", "M_", "MOT"), comentario=("motor", "contactor")),
    ReglaCategoria("Analogicas", direcciones=("%IW*", "%QW*", "%ID*", "%QD*")),
    ReglaCategoria("Entradas_digitales", direcciones=("%I*.*",)),
    ReglaCategoria("Salidas_digitales", direcciones=("%Q*.*",)),
    ReglaCategoria("Marcas", direcciones=("%M*",)),
)


def planificar(tags: list[Tag], reglas: list[ReglaCategoria] | tuple[ReglaCategoria, ...],
               solo_tabla: str | None = None) -> tuple[list[Movimiento], list[str]]:
    """(movimientos necesarios, tags sin categoría). Los tags que ya están en su tabla no se mueven."""
    movimientos, sin_categoria = [], []
    for tag in tags:
        if solo_tabla and tag.tabla != solo_tabla:
            continue
        regla = next((r for r in reglas if r.coincide(tag)), None)
        if regla is None:
            sin_categoria.append(tag.nombre)
        elif regla.tabla != tag.tabla:
            movimientos.append(Movimiento(tag.nombre, tag.direccion, tag.tabla, regla.tabla))
    return movimientos, sin_categoria


def resumen_plan(movimientos: list[Movimiento], sin_categoria: list[str]) -> list[str]:
    por_destino: dict[str, list[Movimiento]] = {}
    for m in movimientos:
        por_destino.setdefault(m.destino, []).append(m)
    lineas = []
    for destino, lista in sorted(por_destino.items()):
        lineas.append(f"{destino} ← {len(lista)} tags")
        lineas += [f"    {m.tag} {m.direccion}  (desde '{m.origen}')" for m in lista]
    if sin_categoria:
        lineas.append(f"Sin categoría (se quedan donde están): {', '.join(sin_categoria)}")
    return lineas
