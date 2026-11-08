"""Catálogo de instrucciones de caja KOP (pines y plantillas tal como las exporta TIA).

`confirmado=True` significa que el formato se verificó en un export real V16/V17
(FlgNet v4). Las no confirmadas funcionan por analogía: si TIA las rechaza,
exporta una hecha a mano y corrige aquí.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...errores import EntradaInvalida


@dataclass(frozen=True)
class DefinicionCaja:
    parte: str                         # atributo Name del <Part>
    flujo_entrada: str                 # pin que recibe el flujo de corriente
    flujo_salida: str                  # pin que entrega el flujo a lo que sigue
    entradas: tuple[str, ...] = ()
    salidas: tuple[str, ...] = ()
    plantillas: dict[str, str] = field(default_factory=dict)   # TemplateValue Name -> valor por defecto
    version: str | None = None
    tipo_instancia: str | None = None  # Datatype para declararla como multiinstancia en Static
    requiere_instancia: bool = False
    cardinalidad: int | None = None
    confirmado: bool = True
    nota: str = ""


_TEMPORIZADOR = {"entradas": ("PT",), "salidas": ("ET",), "plantillas": {"time_type": "Time"},
                 "version": "1.0", "requiere_instancia": True}
_PID_ENTRADAS = ("Setpoint", "Input", "Input_PER", "Disturbance", "ManualEnable", "ManualValue",
                 "ErrorAck", "Reset", "ModeActivate", "Mode")
_PID_SALIDAS = ("ScaledInput", "Output", "Output_PER", "Output_PWM", "SetpointLimit_H", "SetpointLimit_L",
                "InputWarning_H", "InputWarning_L", "State", "Error", "ErrorBits")

CATALOGO: dict[str, DefinicionCaja] = {
    # Temporizadores IEC: el flujo entra por IN y sale por Q
    "TON": DefinicionCaja("TON", "IN", "Q", tipo_instancia="TON_TIME", **_TEMPORIZADOR),
    "TOF": DefinicionCaja("TOF", "IN", "Q", tipo_instancia="TOF_TIME", **_TEMPORIZADOR),
    "TP": DefinicionCaja("TP", "IN", "Q", tipo_instancia="TP_TIME", **_TEMPORIZADOR),
    # Contadores IEC
    "CTU": DefinicionCaja("CTU", "CU", "Q", ("R", "PV"), ("CV",), {"value_type": "Int"}, "1.0",
                          "CTU_INT", True),
    "CTD": DefinicionCaja("CTD", "CD", "Q", ("LD", "PV"), ("CV",), {"value_type": "Int"}, "1.0",
                          "CTD_INT", True),
    "CTUD": DefinicionCaja("CTUD", "CU", "QU", ("CD", "R", "LD", "PV"), ("QD", "CV"), {"value_type": "Int"},
                           "1.0", "CTUD_INT", True, confirmado=False),
    # Flancos como caja con instancia
    "R_TRIG": DefinicionCaja("R_TRIG", "en", "eno", ("CLK",), ("Q",), version="1.0", tipo_instancia="R_TRIG",
                             requiere_instancia=True),
    "F_TRIG": DefinicionCaja("F_TRIG", "en", "eno", ("CLK",), ("Q",), version="1.0", tipo_instancia="F_TRIG",
                             requiere_instancia=True, confirmado=False),
    # Biestables: el operando es la marca que guardan
    "SR": DefinicionCaja("Sr", "s", "q", ("r1", "operand")),
    "RS": DefinicionCaja("Rs", "r", "q", ("s1", "operand")),
    # Transferencia y cálculo (EN/ENO)
    "MOVE": DefinicionCaja("Move", "en", "eno", ("in",), ("out1",), cardinalidad=1),
    "ADD": DefinicionCaja("Add", "en", "eno", ("in1", "in2"), ("out",), {"SrcType": "Int"}, cardinalidad=2),
    "MUL": DefinicionCaja("Mul", "en", "eno", ("in1", "in2"), ("out",), {"SrcType": "Int"}, cardinalidad=2),
    "SUB": DefinicionCaja("Sub", "en", "eno", ("in1", "in2"), ("out",), {"SrcType": "Int"}),
    "DIV": DefinicionCaja("Div", "en", "eno", ("in1", "in2"), ("out",), {"SrcType": "Int"}),
    "CONV": DefinicionCaja("Convert", "en", "eno", ("in",), ("out",), {"SrcType": "Int", "DestType": "Real"}),
    "NORM_X": DefinicionCaja("Normalize", "en", "eno", ("min", "value", "max"), ("out",),
                             {"SrcType": "Int", "DestType": "Real"}),
    "SCALE_X": DefinicionCaja("Scale_X", "en", "eno", ("min", "value", "max"), ("out",),
                              {"SrcType": "Real", "DestType": "Int"}),
    # Regulación: la instancia es el objeto tecnológico (DB global), créalo antes con tia_tecnologia
    "PID_COMPACT": DefinicionCaja("PID_Compact", "en", "eno", _PID_ENTRADAS, _PID_SALIDAS, version="2.2",
                                  requiere_instancia=True, confirmado=False,
                                  nota="Va en un OB de alarma cíclica (OB30). Versión según firmware de la CPU."),
}

_PLANTILLAS_TIPO_CARDINALIDAD = {"Card"}


def definicion(nombre: str) -> DefinicionCaja:
    clave = nombre.upper()
    if clave not in CATALOGO:
        raise EntradaInvalida(f"Instrucción '{nombre}' no está en el catálogo KOP. Disponibles: "
                              f"{', '.join(sorted(CATALOGO))}. Para otras usa SCL o define la caja completa "
                              f"(parte, flujo_entrada, flujo_salida).")
    return CATALOGO[clave]


def tipo_plantilla(nombre: str) -> str:
    return "Cardinality" if nombre in _PLANTILLAS_TIPO_CARDINALIDAD else "Type"


def version_tipo_sistema(tipo_dato: str) -> str | None:
    """Versión que exige TIA al declarar multiinstancias de sistema (TON_TIME, CTU_INT, ...)."""
    for d in CATALOGO.values():
        if d.tipo_instancia and d.tipo_instancia.upper() == tipo_dato.upper():
            return d.version
    return None


def resumen_catalogo() -> list[str]:
    lineas = []
    for clave, d in sorted(CATALOGO.items()):
        estado = "" if d.confirmado else " (sin confirmar en V17)"
        pines = f"flujo {d.flujo_entrada}->{d.flujo_salida}; entradas {', '.join(d.entradas) or '-'}; " \
                f"salidas {', '.join(d.salidas) or '-'}"
        instancia = f"; instancia {d.tipo_instancia or 'DB'}" if d.requiere_instancia else ""
        lineas.append(f"{clave}: {pines}{instancia}{estado}{'; ' + d.nota if d.nota else ''}")
    return lineas
