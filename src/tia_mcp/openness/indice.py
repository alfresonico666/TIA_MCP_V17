"""Índice del programa: todos los bloques leídos (KOP/FUP por XML, SCL por fuente), con caché.

Es la base de referencias cruzadas, árbol de llamadas, diagnóstico y perfil de estilo.
La caché se invalida sola cuando cambia la fecha de modificación de un bloque.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from ..analisis.diagnostico import Programa
from ..scl import usos as usos_scl
from ..simaticml.lector import leer_bloque
from ..simaticml.modelo import BloqueLeido, Llamada
from . import bloques, tags
from .compilacion import compilar
from .sesion import SesionTia

log = logging.getLogger(__name__)
_TIPOS_DATOS = ("GlobalDB", "InstanceDB", "ArrayDB")


@dataclass
class ResultadoIndice:
    bloques: list[BloqueLeido] = field(default_factory=list)
    inconsistentes: list[str] = field(default_factory=list)
    protegidos: list[str] = field(default_factory=list)
    instancias_sin_fb: list[str] = field(default_factory=list)


class IndicePrograma:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, str], BloqueLeido] = {}

    def leer(self, sesion: SesionTia, plc, compilar_antes: bool = True) -> ResultadoIndice:
        todos = list(bloques.recorrer(plc))
        if compilar_antes and any(not b.IsConsistent for b, _ in todos):
            compilar(sesion, plc)  # TIA no exporta bloques inconsistentes
        resultado = ResultadoIndice()
        nombres_codigo = {str(b.Name) for b, _ in todos}
        for bloque, _ in todos:
            info = bloques.info(bloque)
            if info.tipo == "InstanceDB" and info.instancia_de and info.instancia_de not in nombres_codigo:
                resultado.instancias_sin_fb.append(info.nombre)
            if info.tipo in _TIPOS_DATOS:
                continue
            if bool(bloque.IsKnowHowProtected):
                resultado.protegidos.append(info.nombre)
            elif not info.consistente:
                resultado.inconsistentes.append(info.nombre)
            else:
                resultado.bloques.append(self._leer_con_cache(sesion, plc, bloque, info))
        _resolver_llamadas_scl(resultado.bloques, [bloques.info(b) for b, _ in todos])
        return resultado

    def programa(self, sesion: SesionTia, plc) -> Programa:
        indice = self.leer(sesion, plc)
        return Programa(bloques=indice.bloques, tags=tags.todos(sesion, plc),
                        inconsistentes=indice.inconsistentes, instancias_sin_fb=indice.instancias_sin_fb)

    def invalidar(self) -> None:
        self._cache.clear()

    def _leer_con_cache(self, sesion: SesionTia, plc, bloque, info: bloques.InfoBloque) -> BloqueLeido:
        clave = (str(plc.Name), info.nombre, str(bloque.ModifiedDate))
        if clave not in self._cache:
            leido = leer_bloque(bloques.xml_de(sesion, bloque))
            if leido.es_codigo_tokenizado:
                _completar_con_fuente(sesion, plc, bloque, leido)
            self._cache[clave] = leido
        return self._cache[clave]


def _completar_con_fuente(sesion: SesionTia, plc, bloque, leido: BloqueLeido) -> None:
    try:
        fuente = bloques.fuente_de(sesion, plc, bloque)
    except Exception as e:
        log.warning("No se pudo generar la fuente de %s: %s", leido.nombre, e)
        return
    usos, llamadas = usos_scl.analizar(fuente)
    leido.usos.extend(usos)
    leido.llamadas.extend(llamadas)


def _resolver_llamadas_scl(leidos: list[BloqueLeido], infos: list[bloques.InfoBloque]) -> None:
    """En SCL una llamada se escribe con la instancia ("DB_Motor"(...)) o el FC ("FC_X"(...)): se traduce."""
    por_nombre = {i.nombre: i for i in infos}
    for bloque in leidos:
        tipos_static = {m.nombre: m.tipo.strip('"') for m in bloque.interfaz.get("Static", [])}
        resueltas = []
        for llamada in bloque.llamadas:
            if llamada.tipo_bloque != "?":
                resueltas.append(llamada)
                continue
            resuelta = _resolver(llamada, por_nombre, tipos_static)
            if resuelta is not None:
                resueltas.append(resuelta)
        bloque.llamadas[:] = resueltas


def _resolver(llamada: Llamada, por_nombre: dict, tipos_static: dict[str, str]) -> Llamada | None:
    nombre = llamada.bloque
    if nombre.startswith("#"):
        tipo = tipos_static.get(nombre[1:])
        return replace(llamada, bloque=tipo, tipo_bloque="FB", instancia=nombre) if tipo in por_nombre else None
    sin_comillas = nombre.strip('"')
    info = por_nombre.get(sin_comillas)
    if info is None:
        return None  # instrucción de sistema (p. ej. "TON" no aparece así) o tipo no encontrado
    if info.tipo == "InstanceDB" and info.instancia_de:
        return replace(llamada, bloque=info.instancia_de, tipo_bloque="FB", instancia=nombre)
    if info.tipo == "FC":
        return replace(llamada, bloque=sin_comillas, tipo_bloque="FC")
    return None
