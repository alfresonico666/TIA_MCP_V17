"""Genera SimaticML (FlgNet v4) para TIA Portal V17 a partir de los elementos KOP.

Cada elemento se "emite" recibiendo el pin que le da corriente y devuelve el pin
de su salida para que lo use el siguiente. Las bobinas cierran el escalón.
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from ...errores import EntradaInvalida
from .elementos import (
    SECCIONES_FB,
    SECCIONES_FC,
    SECCIONES_OB,
    Bobina,
    Caja,
    Comparacion,
    Contacto,
    ContactoFlanco,
    DefinicionBloque,
    LlamadaBloque,
    Paralelo,
    Red,
    Serie,
    Variable,
)
from .instrucciones import definicion, tipo_plantilla, version_tipo_sistema
from .operandos import instancia, operando

NS_INTERFAZ_V17 = "http://www.siemens.com/automation/Openness/SW/Interface/v5"
NS_FLGNET_V17 = "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4"

_COMPARADORES = {"==": "Eq", "=": "Eq", "<>": "Ne", "!=": "Ne", ">": "Gt", ">=": "Ge", "<": "Lt", "<=": "Le"}
_POWERRAIL = ("powerrail",)
_ENTRADAS_OB_CICLO = (Variable("Initial_Call", "Bool"), Variable("Remanence", "Bool"))  # informativas
_PRIMER_UID = 21  # TIA numera desde 21 dentro de cada red


class _ConstructorRed:
    def __init__(self) -> None:
        self._uid = _PRIMER_UID - 1
        self._accesos: list[str] = []
        self._piezas: list[str] = []
        self._cables: dict[tuple, list[tuple]] = {}
        # TIA exige que TODOS los pines de una caja estén cableados: los libres van a <OpenCon>.
        self._pines_de_cajas: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []

    def _nuevo_uid(self) -> int:
        self._uid += 1
        return self._uid

    def _conectar(self, origen: tuple, destino: tuple) -> None:
        self._cables.setdefault(origen, []).append(destino)

    def _acceso(self, texto: str, tipo_sugerido: str | None = None) -> tuple:
        uid = self._nuevo_uid()
        self._accesos.append(operando(texto, tipo_sugerido).xml(uid))
        return ("ident", uid)

    def _entrada_desde(self, texto: str, uid: int, pin: str, tipo: str | None = None) -> None:
        self._conectar(self._acceso(texto, tipo), ("name", uid, pin))

    def _salida_hacia(self, uid: int, pin: str, texto: str) -> None:
        self._conectar(("name", uid, pin), self._acceso(texto))

    # ------------------------------------------------------------------ emisión
    def emitir(self, elemento, entrada: tuple):
        emisores = {
            Contacto: self._contacto, ContactoFlanco: self._contacto_flanco, Bobina: self._bobina,
            Comparacion: self._comparacion, Caja: self._caja, LlamadaBloque: self._llamada,
            Serie: self._serie, Paralelo: self._paralelo,
        }
        emisor = emisores.get(type(elemento))
        if emisor is None:
            raise EntradaInvalida(f"Elemento KOP desconocido: {elemento!r}")
        return emisor(elemento, entrada)

    def _contacto(self, c: Contacto, entrada: tuple) -> tuple:
        uid = self._nuevo_uid()
        negado = '<Negated Name="operand" />' if c.negado else ""
        self._piezas.append(f'<Part Name="Contact" UId="{uid}">{negado}</Part>' if negado
                            else f'<Part Name="Contact" UId="{uid}" />')
        self._entrada_desde(c.operando, uid, "operand")
        self._conectar(entrada, ("name", uid, "in"))
        return ("name", uid, "out")

    def _contacto_flanco(self, c: ContactoFlanco, entrada: tuple) -> tuple:
        uid = self._nuevo_uid()
        self._piezas.append(f'<Part Name="{c.flanco}Contact" UId="{uid}" />')
        self._entrada_desde(c.operando, uid, "operand")
        self._entrada_desde(c.memoria, uid, "bit")
        self._conectar(entrada, ("name", uid, "pre"))  # los contactos de flanco usan "pre", no "in"
        return ("name", uid, "out")

    def _bobina(self, b: Bobina, entrada: tuple) -> None:
        uid = self._nuevo_uid()
        self._piezas.append(f'<Part Name="{b.tipo}" UId="{uid}" />')
        self._entrada_desde(b.operando, uid, "operand")
        self._conectar(entrada, ("name", uid, "in"))
        # la bobina cierra el escalón

    def _comparacion(self, c: Comparacion, entrada: tuple) -> tuple:
        if c.operador not in _COMPARADORES:
            raise EntradaInvalida(f"Comparador no válido '{c.operador}'. Usa: {', '.join(_COMPARADORES)}.")
        uid = self._nuevo_uid()
        self._piezas.append(f'<Part Name="{_COMPARADORES[c.operador]}" UId="{uid}">'
                            f'<TemplateValue Name="SrcType" Type="Type">{escape(c.tipo)}</TemplateValue></Part>')
        self._conectar(entrada, ("name", uid, "pre"))
        self._entrada_desde(c.a, uid, "in1", c.tipo)
        self._entrada_desde(c.b, uid, "in2", c.tipo)
        return ("name", uid, "out")

    def _caja(self, caja: Caja, entrada: tuple) -> tuple:
        d = definicion(caja.instruccion)
        if d.requiere_instancia and not caja.instancia:
            raise EntradaInvalida(f"{caja.instruccion} necesita `instancia` (#Multiinstancia o \"DB\").")
        _exigir_pines(caja.instruccion, caja.entradas, d.entradas, "entradas")
        _exigir_pines(caja.instruccion, caja.salidas, d.salidas, "salidas")
        uid = self._nuevo_uid()
        instancia_xml = instancia(caja.instancia).xml_instancia(self._nuevo_uid()) if caja.instancia else ""
        plantillas = {**d.plantillas, **caja.plantillas}
        if d.cardinalidad:
            plantillas.setdefault("Card", str(d.cardinalidad))
        plantillas_xml = "".join(f'<TemplateValue Name="{n}" Type="{tipo_plantilla(n)}">{escape(v)}</TemplateValue>'
                                 for n, v in plantillas.items())
        version = caja.version or d.version
        atributo_version = f' Version="{version}"' if version else ""
        self._piezas.append(f'<Part Name="{d.parte}"{atributo_version} UId="{uid}">'
                            f"{instancia_xml}{plantillas_xml}</Part>")
        self._conectar(entrada, ("name", uid, d.flujo_entrada))
        tipo_datos = plantillas.get("SrcType")
        for pin, texto in caja.entradas.items():
            self._entrada_desde(texto, uid, pin, tipo_datos)
        for pin, texto in caja.salidas.items():
            self._salida_hacia(uid, pin, texto)
        salidas_reales = tuple(p for p in (*d.salidas, d.flujo_salida) if p != "eno")
        self._pines_de_cajas.append((uid, d.entradas, salidas_reales))
        return ("name", uid, d.flujo_salida)

    def _llamada(self, llamada: LlamadaBloque, entrada: tuple) -> tuple:
        if llamada.tipo_bloque == "FB" and not llamada.instancia:
            raise EntradaInvalida(f"La llamada al FB {llamada.bloque} necesita `instancia`.")
        uid = self._nuevo_uid()
        instancia_xml = instancia(llamada.instancia).xml_instancia(self._nuevo_uid()) if llamada.instancia else ""
        parametros = "".join(f"<Parameter Name={quoteattr(n)} Section={quoteattr(p.seccion)} "
                             f"Type={quoteattr(p.tipo)} />" for n, p in llamada.parametros.items())
        self._piezas.append(f'<Call UId="{uid}"><CallInfo Name={quoteattr(llamada.bloque)} '
                            f'BlockType="{llamada.tipo_bloque}">{instancia_xml}{parametros}</CallInfo></Call>')
        self._conectar(entrada, ("name", uid, "en"))
        for nombre, p in llamada.parametros.items():
            if p.seccion == "Output":
                self._salida_hacia(uid, nombre, p.operando)
            else:
                self._entrada_desde(p.operando, uid, nombre, p.tipo)
        return ("name", uid, "eno")

    def _serie(self, serie: Serie, entrada: tuple):
        pin = entrada
        for elemento in serie.elementos:
            if pin is None:
                raise EntradaInvalida("Hay elementos después de una bobina en la misma serie.")
            pin = self.emitir(elemento, pin)
        return pin

    def _paralelo(self, paralelo: Paralelo, entrada: tuple) -> tuple:
        salidas = [self.emitir(rama, entrada) for rama in paralelo.ramas]
        if any(s is None for s in salidas):
            raise EntradaInvalida("Las ramas de un paralelo no pueden terminar en bobina; pon la bobina después.")
        uid = self._nuevo_uid()
        self._piezas.append(f'<Part Name="O" UId="{uid}">'
                            f'<TemplateValue Name="Card" Type="Cardinality">{len(salidas)}</TemplateValue></Part>')
        for i, salida in enumerate(salidas, start=1):
            self._conectar(salida, ("name", uid, f"in{i}"))
        return ("name", uid, "out")

    # ------------------------------------------------------------------ XML
    def _cablear_pines_libres(self) -> None:
        conectados = {extremo for origen, destinos in self._cables.items() for extremo in (origen, *destinos)}
        for uid, entradas, salidas in self._pines_de_cajas:
            for pin in entradas:
                if ("name", uid, pin) not in conectados:
                    self._conectar(("open", self._nuevo_uid()), ("name", uid, pin))
            for pin in salidas:
                if ("name", uid, pin) not in conectados:
                    self._conectar(("name", uid, pin), ("open", self._nuevo_uid()))

    def xml(self, ns_flgnet: str) -> str:
        self._cablear_pines_libres()
        cables = []
        for origen, destinos in self._cables.items():
            uid = self._nuevo_uid()
            cables.append(f'<Wire UId="{uid}">' + _conector(origen) + "".join(map(_conector, destinos)) + "</Wire>")
        return (f'<FlgNet xmlns="{ns_flgnet}"><Parts>' + "".join(self._accesos) + "".join(self._piezas)
                + "</Parts><Wires>" + "".join(cables) + "</Wires></FlgNet>")


def _conector(c: tuple) -> str:
    if c[0] == "powerrail":
        return "<Powerrail />"
    if c[0] == "ident":
        return f'<IdentCon UId="{c[1]}" />'
    if c[0] == "open":
        return f'<OpenCon UId="{c[1]}" />'
    return f'<NameCon UId="{c[1]}" Name="{c[2]}" />'


def _exigir_pines(instruccion: str, dados: dict, validos: tuple, que: str) -> None:
    desconocidos = set(dados) - set(validos)
    if desconocidos:
        raise EntradaInvalida(f"{instruccion}: {que} desconocidas {sorted(desconocidos)}. "
                              f"Válidas: {', '.join(validos) or 'ninguna'}.")


def flgnet(logica, ns_flgnet: str = NS_FLGNET_V17) -> str:
    """Solo el <FlgNet> de un escalón (útil para pruebas)."""
    constructor = _ConstructorRed()
    constructor.emitir(logica, _POWERRAIL)
    return constructor.xml(ns_flgnet)


# --------------------------------------------------------------------------- documento
class _Ids:
    """IDs de documento en hexadecimal, como los escribe TIA."""

    def __init__(self) -> None:
        self._n = 0  # el ID 0 es el propio bloque

    def __call__(self) -> str:
        self._n += 1
        return format(self._n, "X")


def _texto_multilingue(ids: _Ids, composicion: str, texto: str, cultura: str) -> str:
    return (f'<MultilingualText ID="{ids()}" CompositionName="{composicion}"><ObjectList>'
            f'<MultilingualTextItem ID="{ids()}" CompositionName="Items"><AttributeList>'
            f"<Culture>{cultura}</Culture><Text>{escape(texto)}</Text>"
            "</AttributeList></MultilingualTextItem></ObjectList></MultilingualText>")


def _miembro(v: Variable, cultura: str, informativo: bool = False) -> str:
    version = v.version or version_tipo_sistema(v.tipo)
    atributos = (f"Name={quoteattr(v.nombre)} Datatype={quoteattr(v.tipo)}"
                 + (f" Version={quoteattr(version)}" if version else "")
                 + (' Informative="true"' if informativo else ""))
    hijos = ""
    if v.comentario:
        hijos += f'<Comment><MultiLanguageText Lang="{cultura}">{escape(v.comentario)}</MultiLanguageText></Comment>'
    if v.valor_inicial:
        hijos += f"<StartValue>{escape(v.valor_inicial)}</StartValue>"
    return f"<Member {atributos}>{hijos}</Member>" if hijos else f"<Member {atributos} />"


def _interfaz(definicion_bloque: DefinicionBloque, cultura: str, ns_interfaz: str) -> str:
    orden = {"FB": SECCIONES_FB, "FC": SECCIONES_FC, "OB": SECCIONES_OB}[definicion_bloque.tipo]
    secciones = {s: list(definicion_bloque.interfaz.get(s, [])) for s in orden}
    if definicion_bloque.tipo == "FC" and not secciones["Return"]:
        secciones["Return"] = [Variable("Ret_Val", "Void")]
    partes = []
    for nombre, declaradas in secciones.items():
        informativa = definicion_bloque.tipo == "OB" and nombre == "Input"
        variables = (_ENTRADAS_OB_CICLO if informativa and definicion_bloque.tipo_ob == "ProgramCycle"
                     else declaradas)
        cuerpo = "".join(_miembro(v, cultura, informativa) for v in variables)
        partes.append(f'<Section Name="{nombre}">{cuerpo}</Section>' if cuerpo else f'<Section Name="{nombre}" />')
    return f'<Interface><Sections xmlns="{ns_interfaz}">' + "".join(partes) + "</Sections></Interface>"


def _unidades(ids: _Ids, redes: list[Red], cultura: str, ns_flgnet: str) -> str:
    return "".join(
        f'<SW.Blocks.CompileUnit ID="{ids()}" CompositionName="CompileUnits"><AttributeList>'
        f"<NetworkSource>{flgnet(red.logica, ns_flgnet)}</NetworkSource>"
        "<ProgrammingLanguage>LAD</ProgrammingLanguage></AttributeList><ObjectList>"
        + _texto_multilingue(ids, "Comment", red.comentario, cultura)
        + _texto_multilingue(ids, "Title", red.titulo, cultura)
        + "</ObjectList></SW.Blocks.CompileUnit>"
        for red in redes
    )


def documento(bloque: DefinicionBloque, cultura: str = "es-ES", ns_interfaz: str = NS_INTERFAZ_V17,
              ns_flgnet: str = NS_FLGNET_V17) -> str:
    """Documento SimaticML completo de un FB, FC u OB en KOP."""
    ids = _Ids()
    atributos = (_interfaz(bloque, cultura, ns_interfaz)
                 + "<MemoryLayout>Optimized</MemoryLayout>"
                 + f"<Name>{escape(bloque.nombre)}</Name><Number>{bloque.numero}</Number>"
                 + "<ProgrammingLanguage>LAD</ProgrammingLanguage>"
                 + (f"<SecondaryType>{escape(bloque.tipo_ob)}</SecondaryType>" if bloque.tipo == "OB" else ""))
    cuerpo = (_texto_multilingue(ids, "Comment", bloque.comentario, cultura)
              + _unidades(ids, bloque.redes, cultura, ns_flgnet)
              + _texto_multilingue(ids, "Title", bloque.titulo, cultura))
    etiqueta = f"SW.Blocks.{bloque.tipo}"
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Document>\n  <Engineering version="V17" />\n'
            f'  <{etiqueta} ID="0">\n    <AttributeList>{atributos}</AttributeList>\n'
            f"    <ObjectList>{cuerpo}</ObjectList>\n  </{etiqueta}>\n</Document>\n")
