"""Lee bloques SimaticML exportados por TIA y los convierte a `BloqueLeido`.

Para KOP/FUP reconstruye la lógica de cada red como texto y registra qué operandos
se leen y escriben: con eso Claude "lee" un escalón y se calculan referencias
cruzadas sin la API de CrossReference (que Openness V17 no tiene).
"""
from __future__ import annotations

from lxml import etree

from .flgnet import RedFlgNet
from .modelo import BloqueLeido, Miembro, RedLeida
from .xml_util import hijo, hijos, local, texto, texto_multilingue

_PREFIJO_BLOQUE = "SW.Blocks."
_ETIQUETA_UDT = "SW.Types.PlcStruct"


def _es_raiz(elemento) -> bool:
    nombre = local(elemento) if isinstance(elemento.tag, str) else ""
    return nombre == _ETIQUETA_UDT or (nombre.startswith(_PREFIJO_BLOQUE) and nombre != "SW.Blocks.CompileUnit")


def leer_bloque(xml: str | bytes) -> BloqueLeido:
    raiz = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    nodo = next((e for e in raiz.iter() if _es_raiz(e)), None)
    if nodo is None:
        raise ValueError("El XML no contiene un bloque (FB/FC/OB/DB) ni un UDT de SimaticML.")
    atributos = hijo(nodo, "AttributeList")
    numero = texto(atributos, "Number")
    bloque = BloqueLeido(
        nombre=texto(atributos, "Name"),
        tipo="UDT" if local(nodo) == _ETIQUETA_UDT else local(nodo).removeprefix(_PREFIJO_BLOQUE),
        numero=int(numero) if numero.isdigit() else None,
        lenguaje=texto(atributos, "ProgrammingLanguage") or "DB",
        instancia_de=texto(atributos, "InstanceOfName") or None,
        interfaz=_leer_interfaz(hijo(atributos, "Interface")),
    )
    objetos = hijo(nodo, "ObjectList")
    bloque.titulo = texto_multilingue(objetos, "Title")
    bloque.comentario = texto_multilingue(objetos, "Comment")
    _leer_redes(objetos, bloque)
    return bloque


# --------------------------------------------------------------------------- interfaz
def _leer_interfaz(interfaz) -> dict[str, list[Miembro]]:
    secciones = hijo(interfaz, "Sections")
    return {s.get("Name"): [_miembro(m) for m in hijos(s, "Member")]
            for s in hijos(secciones, "Section")}


def _miembro(nodo) -> Miembro:
    comentario = next((t.text or "" for c in hijos(nodo, "Comment")
                       for t in c.iter("{*}MultiLanguageText")), "")
    anidados = hijos(nodo, "Member") + [m for s in hijos(nodo, "Sections")
                                        for sec in hijos(s, "Section") for m in hijos(sec, "Member")]
    return Miembro(nombre=nodo.get("Name"), tipo=nodo.get("Datatype", ""), comentario=comentario.strip(),
                   valor_inicial=texto(nodo, "StartValue"), hijos=tuple(_miembro(m) for m in anidados))


# --------------------------------------------------------------------------- redes
def _leer_redes(objetos, bloque: BloqueLeido) -> None:
    unidades = hijos(objetos, "SW.Blocks.CompileUnit")
    for indice, unidad in enumerate(unidades, start=1):
        atributos = hijo(unidad, "AttributeList")
        textos = hijo(unidad, "ObjectList")
        red = RedLeida(indice=indice, lenguaje=texto(atributos, "ProgrammingLanguage"),
                       titulo=texto_multilingue(textos, "Title"),
                       comentario=texto_multilingue(textos, "Comment"))
        fuente = hijo(atributos, "NetworkSource")
        flgnet = hijo(fuente, "FlgNet")
        if flgnet is not None:
            analisis = RedFlgNet(flgnet, indice)
            red.sentencias = analisis.sentencias()
            bloque.usos.extend(analisis.usos)
            bloque.llamadas.extend(analisis.llamadas)
        elif fuente is not None and len(fuente):
            red.sentencias = [f"(red {red.lenguaje} tokenizada: usar la fuente SCL/STL del bloque)"]
        red.vacia = not red.sentencias
        bloque.redes.append(red)
