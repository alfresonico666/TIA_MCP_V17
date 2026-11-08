"""Lee pantallas, plantillas y tablas de tags HMI (WinCC Basic/Comfort, SimaticML V17) exportadas por TIA.

Convierte el XML (100+ KB por pantalla) en un resumen compacto que Claude puede leer: objetos con
posición, tamaño, colores, fuente, textos, eventos (funciones de sistema) y tags animados. Sirve para
"aprender" el diseño de HMI de proyectos anteriores y para revisar lo que el generador produce.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from ..xml_util import hijo, hijos, local, texto

_PREFIJO_OBJETO = "Hmi.Screen."
_RAICES_PANTALLA = ("Hmi.Screen.Screen", "Hmi.Screen.ScreenTemplate", "Hmi.Screen.ScreenPopup")
_ATRIBUTOS_RESUMEN = ("BackColor", "ForeColor", "BorderColor", "BorderWidth", "CornerRadius", "BackFillStyle",
                      "Mode", "Format", "FormatPattern", "Radius", "Flashing")


@dataclass
class Evento:
    nombre: str                       # Click, Press, Release, Loaded...
    funciones: list[str] = field(default_factory=list)   # "SetBit(Cmd_Marcha)", "ActivateScreen(HOME)"


@dataclass
class ObjetoHmi:
    tipo: str                         # Button, TextField, Circle, IOField...
    nombre: str
    x: int
    y: int
    ancho: int
    alto: int
    atributos: dict[str, str] = field(default_factory=dict)
    texto: str = ""
    fuente: str = ""
    eventos: list[Evento] = field(default_factory=list)
    animaciones: list[str] = field(default_factory=list)   # "Appearance(Motor_En_Marcha)"
    tags: list[str] = field(default_factory=list)          # tags de proceso / enlaces
    crudos: dict[str, str] = field(default_factory=dict)   # todos los atributos tal como los exporta TIA
    rangos: list[tuple[str, str, str]] = field(default_factory=list)  # (valor, fondo, texto) de RangeAppearance


@dataclass
class PantallaHmi:
    tipo: str                         # Screen | ScreenTemplate | ScreenPopup
    nombre: str
    numero: str
    ancho: int
    alto: int
    fondo: str
    plantilla: str = ""
    objetos: list[ObjetoHmi] = field(default_factory=list)


@dataclass
class TagHmi:
    nombre: str
    tipo: str
    conexion: str = ""                # vacío = tag interno
    tag_plc: str = ""
    acceso: str = ""                  # Symbolic | Absolute
    direccion: str = ""
    ciclo: str = ""


# --------------------------------------------------------------------------- pantallas
def leer_pantalla(xml: str | bytes) -> PantallaHmi:
    raiz = _parsear(xml)
    nodo = next((e for e in raiz.iter() if isinstance(e.tag, str) and local(e) in _RAICES_PANTALLA), None)
    if nodo is None:
        raise ValueError("El XML no es una pantalla, plantilla o popup HMI de SimaticML.")
    attrs = hijo(nodo, "AttributeList")
    pantalla = PantallaHmi(
        tipo=local(nodo).removeprefix(_PREFIJO_OBJETO), nombre=texto(attrs, "Name"),
        numero=texto(attrs, "Number"), ancho=_entero(texto(attrs, "Width")), alto=_entero(texto(attrs, "Height")),
        fondo=texto(attrs, "BackColor"), plantilla=_enlace(nodo, "Template"))
    for obj in _objetos_de(nodo):
        pantalla.objetos.append(_leer_objeto(obj))
    return pantalla


def _objetos_de(nodo):
    """Objetos de la pantalla: cuelgan de las capas (Hmi.Screen.ScreenLayer, CompositionName='Layers')."""
    for capa in hijos_todos(hijo(nodo, "ObjectList")):
        if local(capa) != "Hmi.Screen.ScreenLayer":
            if local(capa).startswith(_PREFIJO_OBJETO) and capa.get("CompositionName") == "ScreenItems":
                yield capa
            continue
        for e in hijos_todos(hijo(capa, "ObjectList")):
            if local(e).startswith(_PREFIJO_OBJETO) and e.get("CompositionName") == "ScreenItems":
                yield e


def hijos_todos(padre) -> list:
    return [e for e in padre if isinstance(e.tag, str)] if padre is not None else []


def _leer_objeto(nodo) -> ObjetoHmi:
    attrs = hijo(nodo, "AttributeList")
    valores = {local(a): (a.text or "").strip() for a in hijos_todos(attrs)}
    objeto = ObjetoHmi(
        tipo=local(nodo).removeprefix(_PREFIJO_OBJETO), nombre=valores.get("ObjectName", ""),
        x=_entero(valores.get("Left")), y=_entero(valores.get("Top")),
        ancho=_entero(valores.get("Width")), alto=_entero(valores.get("Height")),
        atributos={k: v for k, v in valores.items() if k in _ATRIBUTOS_RESUMEN and v},
        crudos=valores,
    )
    objetos = hijo(nodo, "ObjectList")
    objeto.texto = _texto_visible(objetos)
    objeto.fuente = _fuente(objetos)
    for enlace in hijos_todos(hijo(nodo, "LinkList")):
        nombre = texto(enlace, "Name")
        if nombre:
            objeto.tags.append(f"{local(enlace)}={nombre}")
    for hijo_obj in hijos_todos(objetos):
        etiqueta = local(hijo_obj)
        if etiqueta == "Hmi.Event.Event":
            objeto.eventos.append(_leer_evento(hijo_obj))
        elif etiqueta.startswith("Hmi.Dynamic."):
            objeto.animaciones.append(_leer_animacion(hijo_obj))
            for rango in hijo_obj.iter("{*}Hmi.Dynamic.Range", "Hmi.Dynamic.Range"):
                a = {local(x): (x.text or "") for x in hijos_todos(hijo(rango, "AttributeList"))}
                objeto.rangos.append((a.get("LowerLimit", ""), a.get("BackColor", ""), a.get("ForeColor", "")))
    return objeto


def _leer_evento(nodo) -> Evento:
    evento = Evento(texto(hijo(nodo, "AttributeList"), "Name"))
    for entrada in nodo.iter("{*}Hmi.Event.FunctionListEntry", "Hmi.Event.FunctionListEntry"):
        nombre = texto(hijo(entrada, "AttributeList"), "Name")
        parametros = []
        for p in entrada.iter("{*}Hmi.Event.FunctionListEntryParameter", "Hmi.Event.FunctionListEntryParameter"):
            valor = _enlace(p, "Value") or texto(hijo(p, "AttributeList"), "Value")
            if valor:
                parametros.append(valor)
        evento.funciones.append(f"{nombre}({', '.join(parametros)})")
    return evento


def _leer_animacion(nodo) -> str:
    tipo = local(nodo).removeprefix("Hmi.Dynamic.").removesuffix("Animation")
    tags = [texto(t, "Name") for t in nodo.iter("{*}Tag", "Tag") if texto(t, "Name")]
    rangos = []
    for rango in nodo.iter("{*}Hmi.Dynamic.AppearanceRange", "Hmi.Dynamic.AppearanceRange"):
        a = {local(x): (x.text or "") for x in hijos_todos(hijo(rango, "AttributeList"))}
        rangos.append(f"{a.get('Range', '?')}:{a.get('BackColor', '')}")
    detalle = f" {' '.join(rangos)}" if rangos else ""
    return f"{tipo}({', '.join(tags)}){detalle}"


def _texto_visible(objetos) -> str:
    """Texto del objeto (Text, TextOff/TextOn de botones) sin las etiquetas <body><p>."""
    partes = []
    for mt in hijos(objetos, "MultilingualText"):
        if mt.get("CompositionName") not in ("Text", "TextOff", "TextOn", "Text Off", "Text On"):
            continue
        for item in mt.iter("{*}Text", "Text"):
            contenido = "".join(item.itertext()).strip()
            if contenido and contenido != "Text":
                partes.append(contenido)
                break
    return " / ".join(dict.fromkeys(partes))


def _fuente(objetos) -> str:
    for item in (objetos.iter("{*}Hmi.Globalization.FontItem", "Hmi.Globalization.FontItem")
                 if objetos is not None else []):
        a = hijo(item, "AttributeList")
        return f"{texto(a, 'FontFamily')} {texto(a, 'FontSize')} {texto(a, 'FontStyle')}".strip()
    return ""


def _enlace(nodo, nombre_enlace: str) -> str:
    enlaces = hijo(nodo, "LinkList")
    destino = hijo(enlaces, nombre_enlace)
    return texto(destino, "Name") if destino is not None else ""


def pantalla_como_texto(p: PantallaHmi) -> str:
    lineas = [f"{p.tipo} '{p.nombre}' n.º {p.numero}  {p.ancho}x{p.alto}  fondo={p.fondo}"
              + (f"  plantilla={p.plantilla}" if p.plantilla else "")]
    for o in sorted(p.objetos, key=lambda o: (o.y, o.x)):
        extra = ", ".join(f"{k}={v}" for k, v in o.atributos.items())
        linea = f"  {o.tipo:<16} {o.nombre:<22} ({o.x},{o.y}) {o.ancho}x{o.alto}"
        if o.texto:
            linea += f'  "{o.texto}"'
        if o.fuente:
            linea += f"  [{o.fuente}]"
        if extra:
            linea += f"  {extra}"
        lineas.append(linea)
        lineas += [f"      evento {e.nombre}: {'; '.join(e.funciones)}" for e in o.eventos]
        lineas += [f"      anim {a}" for a in o.animaciones]
        if o.tags:
            lineas.append(f"      enlaces {', '.join(o.tags)}")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- tags
def leer_tabla_tags(xml: str | bytes) -> tuple[str, list[TagHmi]]:
    raiz = _parsear(xml)
    tabla = next((e for e in raiz.iter() if isinstance(e.tag, str) and local(e) == "Hmi.Tag.TagTable"), None)
    if tabla is None:
        raise ValueError("El XML no es una tabla de tags HMI.")
    nombre_tabla = texto(hijo(tabla, "AttributeList"), "Name")
    resultado = []
    for tag in tabla.iter("{*}Hmi.Tag.Tag", "Hmi.Tag.Tag"):
        a = hijo(tag, "AttributeList")
        resultado.append(TagHmi(
            nombre=texto(a, "Name"), tipo=_enlace(tag, "DataType"), conexion=_enlace(tag, "Connection"),
            tag_plc=_enlace(tag, "ControllerTag"), acceso=texto(a, "AddressAccessMode"),
            direccion=texto(a, "LogicalAddress"), ciclo=_enlace(tag, "AcquisitionCycle")))
    return nombre_tabla, resultado


def tabla_tags_como_texto(nombre: str, tags: list[TagHmi]) -> str:
    lineas = [f"Tabla de tags HMI '{nombre}' ({len(tags)})"]
    for t in tags:
        origen = f"{t.conexion} -> {t.tag_plc or t.direccion}" if t.conexion else "interno"
        lineas.append(f"  {t.nombre:<28} {t.tipo:<10} {origen}  [{t.ciclo}]")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- internos
def _parsear(xml: str | bytes):
    datos = xml.encode("utf-8") if isinstance(xml, str) else xml
    return etree.fromstring(datos.lstrip(b"\xef\xbb\xbf"))


def _entero(valor: str | None) -> int:
    try:
        return int(float(valor or 0))
    except ValueError:
        return 0
