"""Ocupación de direcciones absolutas (%I, %Q, %M) a partir de la tabla de variables."""
from __future__ import annotations

import re
from dataclasses import dataclass

_DIRECCION = re.compile(r"^%(?P<area>I|Q|M)(?P<ancho>[XBWD]?)(?P<byte>\d+)(\.(?P<bit>[0-7]))?$", re.IGNORECASE)
_BITS = {"": 1, "X": 1, "B": 8, "W": 16, "D": 32}
_ANCHO_POR_TIPO = {"Bool": "", "Byte": "B", "Char": "B", "SInt": "B", "USInt": "B", "Word": "W", "Int": "W",
                   "UInt": "W", "DWord": "D", "DInt": "D", "UDInt": "D", "Real": "D", "Time": "D"}


@dataclass(frozen=True)
class Rango:
    area: str
    inicio: int     # en bits
    fin: int        # exclusivo
    texto: str

    def se_solapa(self, otro: Rango) -> bool:
        return self.area == otro.area and self.inicio < otro.fin and otro.inicio < self.fin


def rango(direccion: str) -> Rango | None:
    m = _DIRECCION.match(direccion.strip())
    if not m:
        return None
    ancho = m.group("ancho").upper()
    inicio = int(m.group("byte")) * 8 + int(m.group("bit") or 0)
    return Rango(m.group("area").upper(), inicio, inicio + _BITS[ancho], direccion.strip())


def solapamientos(tags: list[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """[(tag A, dirección A, tag B, dirección B)] para tags que comparten bits."""
    rangos = [(nombre, r) for nombre, d in tags if (r := rango(d)) is not None]
    rangos.sort(key=lambda x: (x[1].area, x[1].inicio))
    conflictos = []
    for i, (nombre_a, a) in enumerate(rangos):
        for nombre_b, b in rangos[i + 1:]:
            if b.area != a.area or b.inicio >= a.fin:
                break
            if a.se_solapa(b):
                conflictos.append((nombre_a, a.texto, nombre_b, b.texto))
    return conflictos


def siguiente_libre(tags: list[tuple[str, str]], area: str, tipo: str = "Bool", desde_byte: int = 0) -> str:
    area = area.upper().lstrip("%")
    ancho = _ANCHO_POR_TIPO.get(tipo, "")
    bits = _BITS[ancho]
    ocupados = [r for _, d in tags if (r := rango(d)) is not None and r.area == area]
    paso = 1 if bits == 1 else 8
    inicio = desde_byte * 8
    while True:
        candidato = Rango(area, inicio, inicio + bits, "")
        if not any(candidato.se_solapa(r) for r in ocupados):
            byte, bit = divmod(inicio, 8)
            return f"%{area}{byte}.{bit}" if bits == 1 else f"%{area}{ancho}{byte}"
        inicio += paso
