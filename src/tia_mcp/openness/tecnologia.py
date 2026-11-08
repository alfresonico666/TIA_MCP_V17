"""Objetos tecnológicos (PID_Compact, PID_3Step, PID_Temp, ...): listar, crear, parámetros."""
from __future__ import annotations

import difflib
from collections.abc import Iterator

from ..errores import EntradaInvalida, NoEncontrado, OperacionTiaFallida
from .cargador import implementacion
from .sesion import SesionTia

TIPOS_HABITUALES_S7_1200 = {
    "PID_Compact": "Regulador PID universal con autoajuste (salida continua o PWM)",
    "PID_3Step": "Regulador para válvulas/actuadores motorizados (abrir/cerrar)",
    "PID_Temp": "Regulador de temperatura (calor/frío)",
}


def recorrer(plc) -> Iterator[object]:
    yield from _recorrer_grupo(plc.TechnologicalObjectGroup)


def _recorrer_grupo(grupo) -> Iterator[object]:
    concreto = implementacion(grupo)  # el tipo declarado no expone las subcarpetas
    yield from concreto.TechnologicalObjects
    for subgrupo in getattr(concreto, "Groups", None) or []:
        yield from _recorrer_grupo(subgrupo)


def listar(plc) -> list[tuple[str, str, str]]:
    """[(nombre, tipo, número de DB)]."""
    return [(str(to.Name), _atributo(to, "TypeIdentifier") or _atributo(to, "Type") or "?",
             _atributo(to, "Number") or "?") for to in recorrer(plc)]


def buscar(plc, nombre: str):
    for to in recorrer(plc):
        if str(to.Name) == nombre:
            return to
    raise NoEncontrado("el objeto tecnológico", nombre,
                       difflib.get_close_matches(nombre, [str(t.Name) for t in recorrer(plc)]))


def crear(sesion: SesionTia, plc, nombre: str, tipo: str, version: str) -> str:
    if any(str(t.Name) == nombre for t in recorrer(plc)):
        raise EntradaInvalida(f"Ya existe el objeto tecnológico '{nombre}'.")
    try:
        implementacion(plc.TechnologicalObjectGroup).TechnologicalObjects.Create(
            nombre, tipo, sesion.sis.Version(version))
    except Exception as e:
        raise OperacionTiaFallida(
            f"TIA no pudo crear {tipo} V{version}: {e}. Revisa la versión de la instrucción que admite el "
            f"firmware de la CPU (en TIA: Instrucciones > Tecnología > PID Control)."
        ) from e
    return f"Objeto tecnológico {tipo} '{nombre}' creado (V{version})."


def parametros(plc, nombre: str, filtro: str | None = None) -> list[tuple[str, str]]:
    to = buscar(plc, nombre)
    resultado = []
    for p in to.Parameters:
        nombre_p = str(p.Name)
        if filtro and filtro.lower() not in nombre_p.lower():
            continue
        resultado.append((nombre_p, _valor(p)))
    return resultado


def escribir_parametro(plc, nombre: str, parametro: str, valor) -> str:
    to = buscar(plc, nombre)
    p = to.Parameters.Find(parametro)
    if p is None:
        raise NoEncontrado(f"el parámetro de {nombre}", parametro)
    anterior = _valor(p)
    p.Value = valor
    return f"{nombre}.{parametro}: {anterior} -> {_valor(p)}"


def _valor(parametro) -> str:
    try:
        return str(parametro.Value)
    except Exception as e:
        return f"<no legible: {type(e).__name__}>"


def _atributo(objeto, nombre: str) -> str | None:
    try:
        return str(objeto.GetAttribute(nombre))
    except Exception:
        return None
