"""Formato compacto de respuestas para el LLM: una línea por elemento, con tope y aviso."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

LIMITE_POR_DEFECTO = 200


def lineas(titulo: str, elementos: Sequence[str], limite: int = LIMITE_POR_DEFECTO) -> str:
    """Título + elementos, recortando a `limite` y avisando si se truncó."""
    mostrados = list(elementos[:limite]) if limite > 0 else list(elementos)
    cabecera = f"{titulo} ({len(elementos)})"
    cuerpo = "\n".join(f"  {e}" for e in mostrados) if mostrados else "  (ninguno)"
    aviso = (f"\nAVISO: se muestran {len(mostrados)} de {len(elementos)}; usa `limite` o un filtro."
             if len(mostrados) < len(elementos) else "")
    return f"{cabecera}\n{cuerpo}{aviso}"


def clave_valor(**pares: object) -> str:
    """`Nombre  [k=v, k=v]` omitiendo valores vacíos."""
    return ", ".join(f"{k}={v}" for k, v in pares.items() if v not in (None, "", [], ()))


def fila(nombre: str, **pares: object) -> str:
    detalle = clave_valor(**pares)
    return f"{nombre}  [{detalle}]" if detalle else nombre


def secciones(*bloques: str | None) -> str:
    return "\n\n".join(b for b in bloques if b)


def filtrar(elementos: Iterable[str], filtro: str | None) -> list[str]:
    if not filtro:
        return list(elementos)
    f = filtro.lower()
    return [e for e in elementos if f in e.lower()]
