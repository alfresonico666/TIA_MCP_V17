"""Guardia de rutas: Openness solo trabaja sobre copias de proyectos.

Reglas del equipo:
  1. Nunca abrir un proyecto original de cliente; solo copias en carpetas permitidas.
  2. Nunca descargar al PLC: este servidor no tiene herramientas de descarga ni online.
  3. Si TIA tiene abierto otro proyecto (fuera de las rutas permitidas), no tocarlo.
"""
from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

from .errores import ProyectoAjenoAbierto, RutaNoPermitida


class GuardiaRutas:
    """Una ruta es permitida si ella o alguna carpeta que la contiene coincide con un patrón."""

    def __init__(self, rutas_permitidas: tuple[str, ...]) -> None:
        self._patrones = rutas_permitidas
        self._patrones_normalizados = tuple(_clave(_absoluta(p)) for p in rutas_permitidas)

    @property
    def patrones(self) -> tuple[str, ...]:
        return self._patrones

    def es_permitida(self, ruta: Path | str) -> bool:
        objetivo = _absoluta(ruta)
        candidatas = (objetivo, *objetivo.parents)
        return any(fnmatch(_clave(c), patron)
                   for c in candidatas for patron in self._patrones_normalizados)

    def exigir_permitida(self, ruta: Path | str) -> Path:
        if not self.es_permitida(ruta):
            raise RutaNoPermitida(ruta, self._patrones)
        return _absoluta(ruta)

    def exigir_proyecto_propio(self, ruta_proyecto: Path | str) -> None:
        """Para proyectos que TIA ya tiene abiertos (regla 3)."""
        if not self.es_permitida(ruta_proyecto):
            raise ProyectoAjenoAbierto(ruta_proyecto)


def _absoluta(ruta: Path | str) -> Path:
    """Absoluta y normalizada: elimina '..' para que no se pueda salir de una carpeta permitida."""
    return Path(os.path.abspath(os.path.expanduser(str(ruta))))


def _clave(ruta: Path) -> str:
    """Windows no distingue mayúsculas; se compara en minúsculas y con '\\'."""
    return str(ruta).replace("/", "\\").rstrip("\\").lower()
