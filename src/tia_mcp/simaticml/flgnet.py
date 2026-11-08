"""Análisis de una red KOP/FUP (FlgNet): lógica en texto + usos de operandos.

Un FlgNet es un grafo: `Parts` (accesos a operandos, instrucciones, llamadas) y
`Wires` (cada cable va de un origen a uno o más destinos). Aquí se recorre el grafo
desde cada "sumidero" (bobinas, cajas, llamadas) hacia atrás para obtener la
expresión booleana que lo alimenta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .modelo import Acceso, Llamada, Uso
from .xml_util import hijo, hijos, local, texto

BOBINAS = frozenset({"Coil", "SCoil", "RCoil", "SetCoil", "ResetCoil", "PCoil", "NCoil",
                     "TRCoil", "TPCoil", "TNCoil", "TSCoil", "TOFCoil", "TONCoil", "TPulseCoil",
                     "SdCoil", "SeCoil", "SpCoil", "SsCoil", "SfCoil", "CuCoil", "CdCoil"})
CONTACTOS_FLANCO = {"PContact": "P", "NContact": "N"}      # entrada de flujo: "pre"
CAJAS_FLANCO = {"PBox": "P_TRIG", "NBox": "N_TRIG"}         # entrada de flujo: "in"
BIESTABLES = frozenset({"Sr", "Rs"})
COMPARADORES = {"Eq": "==", "Ne": "<>", "Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<="}
_ELEMENTOS_DE_FLUJO = frozenset({"Contact", "O", "Not", *CONTACTOS_FLANCO, *CAJAS_FLANCO, *COMPARADORES})
_AREAS = {"Input": "I", "Output": "Q", "Memory": "M", "PeripheryInput": "I:P", "PeripheryOutput": "Q:P"}

Conector = tuple  # ("powerrail",) | ("ident", uid) | ("name", uid, pin)


@dataclass
class _Pieza:
    uid: str
    nombre: str             # Contact, Coil, TON, O, Call...
    negados: set[str] = field(default_factory=set)
    instancia: str | None = None
    bloque_llamado: str | None = None
    tipo_llamado: str | None = None

    @property
    def es_llamada(self) -> bool:
        return self.bloque_llamado is not None

    @property
    def etiqueta(self) -> str:
        if self.es_llamada:
            return f'CALL "{self.bloque_llamado}"' + (f" ({self.instancia})" if self.instancia else "")
        return f"{self.instancia} {self.nombre}" if self.instancia else self.nombre


class RedFlgNet:
    def __init__(self, flgnet, indice_red: int) -> None:
        self._red = indice_red
        self._operandos: dict[str, tuple[str, bool]] = {}   # uid -> (texto, es_constante)
        self._piezas: dict[str, _Pieza] = {}
        self._origen_de: dict[Conector, Conector] = {}
        self._destinos_de: dict[Conector, list[Conector]] = {}
        self.usos: list[Uso] = []
        self.llamadas: list[Llamada] = []
        self._leer_partes(hijo(flgnet, "Parts"))
        self._leer_cables(hijo(flgnet, "Wires"))
        self._registrar_usos()

    # ------------------------------------------------------------------ lectura
    def _leer_partes(self, partes) -> None:
        for p in partes if partes is not None else []:
            etiqueta = local(p)
            if etiqueta == "Access":
                self._operandos[p.get("UId")] = texto_operando(p)
            elif etiqueta == "Part":
                self._piezas[p.get("UId")] = _Pieza(
                    uid=p.get("UId"), nombre=p.get("Name"),
                    negados={n.get("Name") for n in hijos(p, "Negated")},
                    instancia=_instancia(p))
            elif etiqueta == "Call":
                self._agregar_llamada(p)

    def _agregar_llamada(self, nodo) -> None:
        info = hijo(nodo, "CallInfo")
        pieza = _Pieza(uid=nodo.get("UId"), nombre="Call", instancia=_instancia(info),
                       bloque_llamado=info.get("Name"), tipo_llamado=info.get("BlockType"))
        self._piezas[pieza.uid] = pieza
        self.llamadas.append(Llamada(pieza.bloque_llamado, pieza.tipo_llamado or "",
                                     pieza.instancia, self._red))

    def _leer_cables(self, cables) -> None:
        for cable in cables if cables is not None else []:
            extremos = [_conector(c) for c in cable if isinstance(c.tag, str)]
            extremos = [e for e in extremos if e is not None]
            if len(extremos) < 2:
                continue
            origen, *destinos = extremos
            self._destinos_de.setdefault(origen, []).extend(destinos)
            for d in destinos:
                self._origen_de[d] = origen

    # ------------------------------------------------------------------ usos
    def _registrar_usos(self) -> None:
        for destino, origen in self._origen_de.items():
            if origen[0] == "ident" and destino[0] == "name":
                self._uso(origen[1], self._acceso_por_pin(destino[1], destino[2]), destino[1])
            elif origen[0] == "name" and destino[0] == "ident":
                self._uso(destino[1], Acceso.ESCRITURA, origen[1])
        for pieza in self._piezas.values():
            if pieza.instancia:
                self.usos.append(Uso(pieza.instancia, Acceso.INSTANCIA, self._nombre_instr(pieza), self._red))

    def _acceso_por_pin(self, uid_pieza: str, pin: str) -> Acceso:
        nombre = self._piezas[uid_pieza].nombre if uid_pieza in self._piezas else ""
        escribe_operando = pin == "operand" and (nombre in BOBINAS or nombre in BIESTABLES)
        if escribe_operando or pin == "bit":  # "bit" = memoria de flanco, siempre se escribe
            return Acceso.ESCRITURA
        return Acceso.LECTURA

    def _uso(self, uid_operando: str, acceso: Acceso, uid_pieza: str) -> None:
        texto_op, es_constante = self._operandos.get(uid_operando, ("?", False))
        if es_constante:
            return
        pieza = self._piezas.get(uid_pieza)
        self.usos.append(Uso(texto_op, acceso, self._nombre_instr(pieza) if pieza else "?", self._red))

    @staticmethod
    def _nombre_instr(pieza: _Pieza) -> str:
        return f"Call {pieza.bloque_llamado}" if pieza.es_llamada else pieza.nombre

    # ------------------------------------------------------------------ lógica en texto
    def sentencias(self) -> list[str]:
        resultado = []
        for pieza in self._piezas.values():
            if pieza.nombre in BOBINAS:
                resultado.append(self._sentencia_bobina(pieza))
            elif self._es_caja(pieza):
                resultado.append(self._sentencia_caja(pieza))
        return resultado

    @staticmethod
    def _es_caja(pieza: _Pieza) -> bool:
        return pieza.es_llamada or pieza.nombre not in _ELEMENTOS_DE_FLUJO

    def _sentencia_bobina(self, pieza: _Pieza) -> str:
        operando = self._operando_en(pieza.uid, "operand")
        condicion = self._entrada(pieza.uid, "in") or "1"
        if pieza.nombre == "Coil":
            return f"{operando} := {_quitar_parentesis(condicion)}"
        if pieza.nombre == "SCoil":
            return f"S {operando}  SI {_quitar_parentesis(condicion)}"
        if pieza.nombre == "RCoil":
            return f"R {operando}  SI {_quitar_parentesis(condicion)}"
        return f"{pieza.nombre} {operando}  SI {_quitar_parentesis(condicion)}"

    def _sentencia_caja(self, pieza: _Pieza) -> str:
        entradas, salidas = [], []
        for (tipo, uid, *pin), origen in self._origen_de.items():
            if tipo == "name" and uid == pieza.uid:
                entradas.append(f"{pin[0]}:={_quitar_parentesis(self._expresion(origen))}")
        for origen, destinos in self._destinos_de.items():
            if origen[0] == "name" and origen[1] == pieza.uid:
                salidas += [f"{origen[2]}=>{self._operandos.get(d[1], ('?',))[0]}"
                            for d in destinos if d[0] == "ident"]
        return f"{pieza.etiqueta}({', '.join(entradas + salidas)})"

    def _entrada(self, uid: str, pin: str) -> str | None:
        origen = self._origen_de.get(("name", uid, pin))
        return self._expresion(origen) if origen is not None else None

    def _operando_en(self, uid: str, pin: str) -> str:
        origen = self._origen_de.get(("name", uid, pin))
        return self._expresion(origen) if origen is not None else "?"

    def _expresion(self, origen: Conector) -> str:
        if origen[0] == "powerrail":
            return "1"
        if origen[0] == "ident":
            return self._operandos.get(origen[1], ("?", False))[0]
        return self._salida(origen[1], origen[2])

    def _salida(self, uid: str, pin: str) -> str:
        pieza = self._piezas.get(uid)
        if pieza is None:
            return "?"
        nombre = pieza.nombre
        if nombre == "Contact":
            termino = self._operando_en(uid, "operand")
            termino = f"NOT {termino}" if "operand" in pieza.negados else termino
            return _y(self._entrada(uid, "in"), termino)
        if nombre in CONTACTOS_FLANCO:
            flanco = f"{CONTACTOS_FLANCO[nombre]}({self._operando_en(uid, 'operand')})"
            return _y(self._entrada(uid, "pre"), flanco)
        if nombre in CAJAS_FLANCO:
            return f"{CAJAS_FLANCO[nombre]}({self._entrada(uid, 'in') or '1'})"
        if nombre in COMPARADORES:
            comparacion = f"{self._operando_en(uid, 'in1')} {COMPARADORES[nombre]} {self._operando_en(uid, 'in2')}"
            return _y(self._entrada(uid, "pre"), comparacion)
        if nombre == "O":
            ramas = [self._expresion(o) for (t, u, *p), o in self._origen_de.items()
                     if t == "name" and u == uid and p[0].startswith("in")]
            return "(" + " OR ".join(ramas) + ")" if len(ramas) > 1 else (ramas[0] if ramas else "?")
        if nombre == "Not":
            return f"NOT ({self._entrada(uid, 'in') or '1'})"
        if nombre in BOBINAS:
            return self._entrada(uid, "in") or "1"
        nombre_salida = "ENO" if pin == "eno" else pin
        return f"{pieza.instancia or pieza.etiqueta}.{nombre_salida}"


# --------------------------------------------------------------------------- operandos
def texto_operando(acceso) -> tuple[str, bool]:
    """Texto de un <Access> tal como se escribe en TIA y si es constante."""
    alcance = acceso.get("Scope", "")
    if alcance in ("LiteralConstant", "TypedConstant"):
        constante = hijo(acceso, "Constant")
        return texto(constante, "ConstantValue"), True
    if alcance == "GlobalConstant":
        return f'"{hijo(acceso, "Constant").get("Name")}"', True
    if alcance == "Address":
        return _direccion_absoluta(hijo(acceso, "Address")), False
    # <Access> usa <Symbol><Component/>; <Instance> pone los <Component/> directamente.
    contenedor = hijo(acceso, "Symbol")
    if contenedor is None:
        contenedor = acceso
    partes = [_componente(c) for c in hijos(contenedor, "Component")]
    if not partes:
        return alcance or "?", False
    if alcance == "LocalVariable":
        return "#" + ".".join(partes), False
    return ".".join([f'"{partes[0]}"', *partes[1:]]), False


def _componente(componente) -> str:
    nombre = componente.get("Name", "?")
    indices = [texto_operando(a)[0] for a in hijos(componente, "Access")]
    if indices:
        nombre += "[" + ",".join(indices) + "]"
    rebanada = componente.get("SliceAccessModifier")
    return f"{nombre}.%{rebanada.upper()}" if rebanada else nombre


def _direccion_absoluta(direccion) -> str:
    if direccion is None:
        return "%?"
    area = _AREAS.get(direccion.get("Area", ""), direccion.get("Area", "?"))
    desplazamiento = int(direccion.get("BitOffset", "0"))
    if direccion.get("Type") == "Bool":
        return f"%{area}{desplazamiento // 8}.{desplazamiento % 8}"
    return f"%{area}{desplazamiento // 8}"


def _instancia(nodo) -> str | None:
    instancia = hijo(nodo, "Instance") if nodo is not None else None
    if instancia is None:
        return None
    return texto_operando(instancia)[0]


def _conector(nodo) -> Conector | None:
    etiqueta = local(nodo)
    if etiqueta == "Powerrail":
        return ("powerrail",)
    if etiqueta == "IdentCon":
        return ("ident", nodo.get("UId"))
    if etiqueta == "NameCon":
        return ("name", nodo.get("UId"), nodo.get("Name"))
    return None  # OpenCon y otros: extremos sin conexión


def _y(previo: str | None, termino: str) -> str:
    if previo in (None, "1"):
        return termino
    return f"{previo} AND {termino}"


def _quitar_parentesis(expresion: str) -> str:
    if expresion.startswith("(") and expresion.endswith(")") and expresion.count("(") == 1:
        return expresion[1:-1]
    return expresion
