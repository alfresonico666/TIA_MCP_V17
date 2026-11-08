"""Utilidades XML independientes del namespace (SimaticML cambia de versión de namespace)."""
from __future__ import annotations


def local(elemento) -> str:
    """Nombre de la etiqueta sin namespace."""
    etiqueta = elemento.tag
    return etiqueta.split("}", 1)[1] if isinstance(etiqueta, str) and "}" in etiqueta else str(etiqueta)


def hijo(padre, etiqueta: str):
    if padre is None:
        return None
    return next((e for e in padre if isinstance(e.tag, str) and local(e) == etiqueta), None)


def hijos(padre, etiqueta: str) -> list:
    if padre is None:
        return []
    return [e for e in padre if isinstance(e.tag, str) and local(e) == etiqueta]


def texto(padre, etiqueta: str) -> str:
    nodo = hijo(padre, etiqueta)
    return (nodo.text or "").strip() if nodo is not None else ""


def texto_multilingue(objetos, composicion: str) -> str:
    """Texto de un MultilingualText (Title/Comment); toma el primer idioma no vacío."""
    for mt in hijos(objetos, "MultilingualText"):
        if mt.get("CompositionName") != composicion:
            continue
        for nodo in mt.iter("{*}Text"):
            if nodo.text and nodo.text.strip():
                return nodo.text.strip()
    return ""
