"""Sesión con TIA Portal: conexión (adjuntar o iniciar) y proyecto activo.

Todo lo de este módulo se ejecuta dentro del hilo de `EjecutorTia`.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..configuracion import Configuracion
from ..errores import ErrorTia, SinProyectoAbierto, TiaNoConectado
from ..seguridad import GuardiaRutas
from .cargador import ApiOpenness, api

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcesoTia:
    pid: int
    modo: str
    proyecto: str | None


class SesionTia:
    def __init__(self, config: Configuracion, guardia: GuardiaRutas) -> None:
        self.config = config
        self.guardia = guardia
        self._tia = None
        self._iniciado_por_nosotros = False
        self._proyecto = None

    # ------------------------------------------------------------------ API .NET
    @property
    def api(self) -> ApiOpenness:
        return api(self.config)

    @property
    def eng(self):
        return self.api.engineering

    @property
    def sis(self):
        return self.api.sistema

    # ------------------------------------------------------------------ conexión
    def procesos(self) -> list[ProcesoTia]:
        return [ProcesoTia(int(p.Id), str(p.Mode), _ruta_o_none(p.ProjectPath))
                for p in self.eng.TiaPortal.GetProcesses()]

    def conectar(self, con_interfaz: bool = True, pid: int | None = None) -> str:
        """Se adjunta a un TIA abierto (el indicado o el primero); si no hay, inicia uno."""
        if self.conectado:
            return "Ya estaba conectado a TIA Portal."
        procesos = list(self.eng.TiaPortal.GetProcesses())
        elegido = next((p for p in procesos if pid is None or int(p.Id) == pid), None)
        if elegido is not None:
            # La primera vez TIA muestra un aviso de seguridad de Openness: "Sí a todo".
            self._tia = elegido.Attach()
            self._iniciado_por_nosotros = False
            self._adoptar_proyecto_abierto()
            return f"Conectado al TIA abierto (PID {elegido.Id})."
        if pid is not None:
            raise ErrorTia(f"No hay un TIA Portal con PID {pid}.")
        modo = self.eng.TiaPortalMode.WithUserInterface if con_interfaz \
            else self.eng.TiaPortalMode.WithoutUserInterface
        self._tia = self.eng.TiaPortal(modo)
        self._iniciado_por_nosotros = True
        return f"TIA Portal V17 iniciado {'con' if con_interfaz else 'sin'} interfaz."

    def desconectar(self) -> str:
        if self._tia is None:
            return "No había conexión."
        cerrar = self._iniciado_por_nosotros
        self._tia.Dispose()  # si lo iniciamos nosotros, Dispose también cierra TIA
        self._tia, self._proyecto = None, None
        return "TIA cerrado (lo había iniciado el servidor)." if cerrar \
            else "Desconectado; TIA sigue abierto para el usuario."

    @property
    def conectado(self) -> bool:
        if self._tia is None:
            return False
        try:
            _ = self._tia.Projects.Count  # falla si el usuario cerró TIA
            return True
        except Exception:
            log.warning("Se perdió la conexión con TIA; se reinicia la sesión.")
            self._tia, self._proyecto = None, None
            return False

    @property
    def tia(self):
        if not self.conectado:
            raise TiaNoConectado()
        return self._tia

    # ------------------------------------------------------------------ proyecto
    @property
    def proyecto(self):
        if self._proyecto is None:
            self._adoptar_proyecto_abierto()
        if self._proyecto is None:
            raise SinProyectoAbierto()
        return self._proyecto

    @property
    def hay_proyecto(self) -> bool:
        return self._proyecto is not None

    def usar_proyecto(self, proyecto) -> None:
        self.guardia.exigir_proyecto_propio(ruta_proyecto(proyecto))
        self._proyecto = proyecto

    def olvidar_proyecto(self) -> None:
        self._proyecto = None

    @contextmanager
    def proyecto_temporal(self, proyecto) -> Iterator[None]:
        """Trabaja sobre otro proyecto (p. ej. uno abierto en solo lectura para aprender) y vuelve al anterior."""
        anterior = self._proyecto
        self._proyecto = proyecto
        try:
            yield
        finally:
            self._proyecto = anterior

    def _adoptar_proyecto_abierto(self) -> None:
        abiertos = list(self.tia.Projects)
        if abiertos:
            self.usar_proyecto(abiertos[0])  # lanza ProyectoAjenoAbierto si no es una copia


def ruta_proyecto(proyecto) -> Path:
    return Path(str(proyecto.Path.FullName))


def _ruta_o_none(info_archivo) -> str | None:
    return str(info_archivo.FullName) if info_archivo is not None else None
