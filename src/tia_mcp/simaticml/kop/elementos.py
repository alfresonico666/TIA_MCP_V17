"""Elementos con los que se describe un escalón KOP.

    Serie(
        Paralelo(Contacto("#Marcha"), Contacto("#Motor")),     # retención
        Contacto("#Paro_NC"),
        Caja("TON", instancia="#T_Arranque", entradas={"PT": "T#5s"}),
        Bobina("#Motor"),
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...errores import EntradaInvalida


@dataclass(frozen=True)
class Contacto:
    operando: str
    negado: bool = False


@dataclass(frozen=True)
class ContactoFlanco:
    """Detecta flanco P (subida) o N (bajada) de `operando`; `memoria` guarda el estado anterior."""
    operando: str
    memoria: str
    flanco: str = "P"

    def __post_init__(self) -> None:
        if self.flanco not in ("P", "N"):
            raise EntradaInvalida("El flanco debe ser 'P' o 'N'.")


@dataclass(frozen=True)
class Bobina:
    """tipo: 'Coil' (normal), 'SCoil' (set), 'RCoil' (reset)."""
    operando: str
    tipo: str = "Coil"

    def __post_init__(self) -> None:
        if self.tipo not in ("Coil", "SCoil", "RCoil"):
            raise EntradaInvalida(f"Tipo de bobina no soportado: {self.tipo}")


@dataclass(frozen=True)
class Comparacion:
    """Contacto de comparación: a <operador> b, con tipo de dato (Int, Real, DInt...)."""
    a: str
    operador: str
    b: str
    tipo: str = "Int"


@dataclass(frozen=True)
class Caja:
    """Instrucción de caja del catálogo (TON, CTU, MOVE, ADD, PID_COMPACT, ...)."""
    instruccion: str
    instancia: str | None = None
    entradas: dict[str, str] = field(default_factory=dict)
    salidas: dict[str, str] = field(default_factory=dict)
    plantillas: dict[str, str] = field(default_factory=dict)  # p. ej. {"SrcType": "Real"}
    version: str | None = None


@dataclass(frozen=True)
class Parametro:
    seccion: str     # Input | Output | InOut
    tipo: str        # tipo de dato del parámetro en el bloque llamado
    operando: str


@dataclass(frozen=True)
class LlamadaBloque:
    """Llamada a un FB (con instancia: "DB_X" o #Multiinstancia) o a un FC (sin instancia)."""
    bloque: str
    tipo_bloque: str = "FB"
    instancia: str | None = None
    parametros: dict[str, Parametro] = field(default_factory=dict)


@dataclass
class Serie:
    elementos: list

    def __init__(self, *elementos) -> None:
        if not elementos:
            raise EntradaInvalida("Una Serie necesita al menos un elemento.")
        self.elementos = list(elementos)


@dataclass
class Paralelo:
    ramas: list

    def __init__(self, *ramas) -> None:
        if len(ramas) < 2:
            raise EntradaInvalida("Un Paralelo necesita al menos 2 ramas.")
        self.ramas = list(ramas)


@dataclass(frozen=True)
class Red:
    titulo: str
    logica: object
    comentario: str = ""


@dataclass(frozen=True)
class Variable:
    """Variable de la interfaz de un bloque."""
    nombre: str
    tipo: str = "Bool"
    comentario: str = ""
    valor_inicial: str = ""
    version: str | None = None   # para tipos de sistema (TON_TIME -> "1.0")


SECCIONES_FB = ("Input", "Output", "InOut", "Static", "Temp", "Constant")
SECCIONES_FC = ("Input", "Output", "InOut", "Temp", "Constant", "Return")
SECCIONES_OB = ("Input", "Temp", "Constant")


@dataclass
class DefinicionBloque:
    tipo: str                                   # FB | FC | OB
    nombre: str
    numero: int
    redes: list[Red]
    interfaz: dict[str, list[Variable]] = field(default_factory=dict)
    titulo: str = ""
    comentario: str = ""
    tipo_ob: str = "ProgramCycle"               # solo OB: ProgramCycle, CyclicInterrupt, Startup...

    def __post_init__(self) -> None:
        if self.tipo not in ("FB", "FC", "OB"):
            raise EntradaInvalida(f"Tipo de bloque KOP no soportado: {self.tipo} (FB, FC u OB).")
        permitidas = {"FB": SECCIONES_FB, "FC": SECCIONES_FC, "OB": SECCIONES_OB}[self.tipo]
        sobrantes = set(self.interfaz) - set(permitidas)
        if sobrantes:
            raise EntradaInvalida(f"Secciones no válidas para {self.tipo}: {', '.join(sorted(sobrantes))}. "
                                  f"Permitidas: {', '.join(permitidas)}.")
        if not self.redes:
            raise EntradaInvalida("El bloque necesita al menos una red (TIA no importa redes KOP vacías).")
