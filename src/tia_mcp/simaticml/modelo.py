"""Modelo de un bloque leído desde SimaticML (independiente de TIA)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Acceso(str, Enum):
    LECTURA = "lectura"
    ESCRITURA = "escritura"
    INSTANCIA = "instancia"  # DB/multiinstancia usada por una llamada o caja


@dataclass(frozen=True)
class Uso:
    """Un operando usado en una red: base de las referencias cruzadas."""
    operando: str          # tal como se ve en TIA: "Motor", #Marcha, "DB_X".campo, T#5s
    acceso: Acceso
    instruccion: str       # Contact, Coil, TON, Call FB_X, ...
    red: int               # 1 = primera red
    es_constante: bool = False


@dataclass(frozen=True)
class Llamada:
    bloque: str
    tipo_bloque: str       # FB, FC
    instancia: str | None
    red: int


@dataclass
class RedLeida:
    indice: int
    titulo: str
    comentario: str
    lenguaje: str
    sentencias: list[str] = field(default_factory=list)  # lógica en texto
    vacia: bool = False


@dataclass(frozen=True)
class Miembro:
    nombre: str
    tipo: str
    comentario: str = ""
    valor_inicial: str = ""
    hijos: tuple[Miembro, ...] = ()


@dataclass
class BloqueLeido:
    nombre: str
    tipo: str              # FB, FC, OB, GlobalDB, InstanceDB, ...
    numero: int | None
    lenguaje: str
    titulo: str = ""
    comentario: str = ""
    interfaz: dict[str, list[Miembro]] = field(default_factory=dict)
    redes: list[RedLeida] = field(default_factory=list)
    usos: list[Uso] = field(default_factory=list)
    llamadas: list[Llamada] = field(default_factory=list)
    instancia_de: str | None = None  # para DB de instancia

    @property
    def es_codigo_tokenizado(self) -> bool:
        """SCL/STL vienen tokenizados en XML; se leen mejor como fuente externa."""
        return self.lenguaje in ("SCL", "STL")
