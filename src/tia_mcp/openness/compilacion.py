"""Compilación y lectura estructurada de mensajes del compilador."""
from __future__ import annotations

from dataclasses import dataclass, field

from .sesion import SesionTia

_GRAVES = ("Error", "Warning")


@dataclass(frozen=True)
class MensajeCompilacion:
    gravedad: str        # Error | Warning
    ubicacion: str       # PLC_1 › Bloques de programa › FB_Motor › Red 2
    texto: str


@dataclass
class ResultadoCompilacion:
    estado: str
    errores: int
    advertencias: int
    mensajes: list[MensajeCompilacion] = field(default_factory=list)

    @property
    def correcto(self) -> bool:
        return self.errores == 0

    def resumen(self) -> str:
        cabecera = f"Compilación: {self.estado} | errores: {self.errores} | advertencias: {self.advertencias}"
        detalle = [f"  [{m.gravedad}] {m.ubicacion}: {m.texto}" for m in self.mensajes]
        return "\n".join([cabecera, *detalle])


def compilar(sesion: SesionTia, objeto) -> ResultadoCompilacion:
    """Compila un PlcSoftware o un bloque. Solo se reportan las hojas del árbol de mensajes."""
    resultado = objeto.GetService[sesion.eng.ICompilable]().Compile()
    mensajes: list[MensajeCompilacion] = []
    _recolectar(resultado.Messages, [], mensajes)
    return ResultadoCompilacion(estado=str(resultado.State), errores=int(resultado.ErrorCount),
                                advertencias=int(resultado.WarningCount), mensajes=mensajes)


def _recolectar(mensajes, ruta: list[str], salida: list[MensajeCompilacion]) -> None:
    for mensaje in mensajes:
        tramo = str(mensaje.Path or "").strip()
        ruta_actual = [*ruta, tramo] if tramo else ruta
        hijos = list(mensaje.Messages)
        if hijos:
            _recolectar(hijos, ruta_actual, salida)
        elif str(mensaje.State) in _GRAVES:
            salida.append(MensajeCompilacion(gravedad=str(mensaje.State), ubicacion=" › ".join(ruta_actual),
                                             texto=str(mensaje.Description or "").strip()))
