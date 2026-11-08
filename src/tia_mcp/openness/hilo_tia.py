"""Hilo dedicado para Openness.

Los objetos de TIA Openness deben usarse siempre desde el mismo hilo, y el SDK de
MCP ejecuta cada herramienta en un hilo distinto. `EjecutorTia` serializa todas
las llamadas en un único hilo con apartamento STA (como piden los ejemplos de
Siemens) y las expone como corrutinas.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

log = logging.getLogger(__name__)
T = TypeVar("T")

_COINIT_APARTMENTTHREADED = 0x2
TIEMPO_MAXIMO_POR_DEFECTO_S = 600  # compilar o abrir proyectos grandes puede tardar minutos


def _iniciar_hilo_sta() -> None:
    resultado = ctypes.windll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    log.debug("Hilo Openness inicializado como STA (HRESULT=%s)", resultado)


class EjecutorTia:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="openness",
                                        initializer=_iniciar_hilo_sta)

    async def ejecutar(self, funcion: Callable[..., T], *args,
                       tiempo_maximo_s: float = TIEMPO_MAXIMO_POR_DEFECTO_S, **kwargs) -> T:
        futuro = self._pool.submit(funcion, *args, **kwargs)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(futuro), tiempo_maximo_s)
        except TimeoutError as e:
            raise TimeoutError(
                f"TIA no respondió en {tiempo_maximo_s:.0f} s. La operación sigue en curso dentro de "
                f"TIA; espera y consulta el estado antes de repetirla (¿hay un diálogo abierto en TIA?)."
            ) from e

    def ejecutar_sincrono(self, funcion: Callable[..., T], *args, **kwargs) -> T:
        """Para scripts y pruebas fuera del bucle asíncrono."""
        return self._pool.submit(funcion, *args, **kwargs).result()

    def cerrar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
