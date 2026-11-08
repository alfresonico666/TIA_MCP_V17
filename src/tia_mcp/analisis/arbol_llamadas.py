"""Árbol de llamadas OB → FB/FC → ... y bloques que nunca se ejecutan."""
from __future__ import annotations

from collections import defaultdict

from ..simaticml.modelo import BloqueLeido, Llamada

_TIPOS_CODIGO = ("FB", "FC")


def llamadas_por_bloque(bloques: list[BloqueLeido]) -> dict[str, list[Llamada]]:
    return {b.nombre: b.llamadas for b in bloques}


def llamadores(bloques: list[BloqueLeido], nombre: str) -> list[tuple[str, int, str | None]]:
    """[(bloque que llama, red, instancia)]."""
    return [(b.nombre, ll.red, ll.instancia) for b in bloques for ll in b.llamadas if ll.bloque == nombre]


def raices(bloques: list[BloqueLeido]) -> list[str]:
    return sorted(b.nombre for b in bloques if b.tipo == "OB")


def arbol_texto(bloques: list[BloqueLeido], raiz: str | None = None) -> list[str]:
    grafo = llamadas_por_bloque(bloques)
    lineas: list[str] = []
    for inicio in [raiz] if raiz else raices(bloques):
        _dibujar(grafo, inicio, 0, [], lineas, None)
    return lineas


def _dibujar(grafo, nombre: str, nivel: int, camino: list[str], lineas: list[str], instancia: str | None) -> None:
    sufijo = f"  ({instancia})" if instancia else ""
    if nombre in camino:
        lineas.append(f"{'  ' * nivel}{nombre}{sufijo}  [RECURSIÓN]")
        return
    lineas.append(f"{'  ' * nivel}{nombre}{sufijo}")
    vistos: set[tuple[str, str | None]] = set()
    for llamada in grafo.get(nombre, []):
        clave = (llamada.bloque, llamada.instancia)
        if clave not in vistos:
            vistos.add(clave)
            _dibujar(grafo, llamada.bloque, nivel + 1, [*camino, nombre], lineas, llamada.instancia)


def alcanzables(bloques: list[BloqueLeido]) -> set[str]:
    grafo = llamadas_por_bloque(bloques)
    pendientes, vistos = list(raices(bloques)), set()
    while pendientes:
        actual = pendientes.pop()
        if actual in vistos:
            continue
        vistos.add(actual)
        pendientes += [ll.bloque for ll in grafo.get(actual, [])]
    return vistos


def no_llamados(bloques: list[BloqueLeido]) -> list[str]:
    """FB/FC que ningún OB ejecuta (directa o indirectamente)."""
    vivos = alcanzables(bloques)
    return sorted(b.nombre for b in bloques if b.tipo in _TIPOS_CODIGO and b.nombre not in vivos)


def instancias_compartidas(bloques: list[BloqueLeido]) -> dict[str, list[str]]:
    """Instancias (DB o multiinstancia) usadas por más de una llamada/caja: casi siempre un error."""
    usos: dict[str, list[str]] = defaultdict(list)
    for b in bloques:
        for u in b.usos:
            if u.acceso.value == "instancia":
                clave = u.operando if u.operando.startswith('"') else f"{b.nombre}:{u.operando}"
                usos[clave].append(f"{b.nombre} red {u.red} ({u.instruccion})")
    return {instancia: lugares for instancia, lugares in usos.items() if len(lugares) > 1}
