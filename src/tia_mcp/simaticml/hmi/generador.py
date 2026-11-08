"""Generador de SimaticML HMI (WinCC Basic/Comfort V17): pantallas, tablas de tags y listas de textos.

Las pantallas se describen con un dict/JSON y se construyen clonando PROTOTIPOS neutros copiados de un
export real de V17 (`prototipos/*.xml`, ver scripts/extraer_prototipos_hmi.py). Ejemplo:

    {"nombre": "Principal", "numero": 1, "fondo": "0, 0, 0",
     "objetos": [
       {"tipo": "rectangulo", "x": 127, "y": 0, "ancho": 353, "alto": 271, "fondo": "247, 243, 247"},
       {"tipo": "texto", "x": 133, "y": 0, "ancho": 343, "alto": 48, "texto": "ARRANQUE Y PARO",
        "fuente": {"tamano": 36, "estilo": "Bold, Italic"}, "color": "49, 52, 74"},
       {"tipo": "boton", "nombre": "Btn_Marcha", "x": 140, "y": 180, "ancho": 100, "alto": 40,
        "texto": "MARCHA", "fondo": "0, 160, 0",
        "al_pulsar": [["SetBit", "Cmd_Marcha"]], "al_soltar": [["ResetBit", "Cmd_Marcha"]]},
       {"tipo": "circulo", "x": 300, "y": 100, "ancho": 33, "alto": 33,
        "apariencia": {"tag": "Motor_En_Marcha", "rangos": [[0, "51, 51, 51"], [1, "0, 255, 0"]]}},
       {"tipo": "campo_es", "tag": "Estado", "x": 300, "y": 150, "ancho": 60, "alto": 30, "formato": "999"},
       {"tipo": "campo_simbolico", "tag": "Sel_Estilo", "lista": "Estilos", "x": 140, "y": 60,
        "ancho": 150, "alto": 30},
       {"tipo": "fecha_hora", "x": 395, "y": 0, "ancho": 85, "alto": 22, "fecha": true, "hora": true},
       {"tipo": "linea", "x1": 147, "y1": 44, "x2": 434, "y2": 44, "color": "255, 203, 0", "grosor": 3}]}

Eventos de botón: `al_click`, `al_pulsar`, `al_soltar` → lista de [funcion, argumentos...]. Funciones:
SetBit, ResetBit, InvertBit (tag) · ActivateScreen (pantalla) · SetTag (tag, valor).
Animaciones (cualquier objeto): `apariencia` {tag, rangos[[valor, fondo(, texto)]]} y
`visible_si` {tag, desde, hasta, visible=true}.
"""
from __future__ import annotations

import copy
from functools import cache
from pathlib import Path

from lxml import etree

DIR_PROTOTIPOS = Path(__file__).parent / "prototipos"
CULTURAS_POR_DEFECTO = ("es-MX", "en-US")
FUENTE_POR_DEFECTO = "Tahoma"

TIPOS = {  # tipo en la especificación -> prototipo
    "rectangulo": "Rectangle", "texto": "TextField", "boton": "Button", "circulo": "Circle",
    "campo_es": "IOField", "campo_simbolico": "SymbolicIOField", "fecha_hora": "DateTimeField", "linea": "Line",
}
_EVENTOS = {"al_click": "Click", "al_pulsar": "Press", "al_soltar": "Release", "al_cambiar": "Change"}
# Valores neutros por tipo (los prototipos conservan colores del export de origen); la especificación manda.
_POR_DEFECTO = {
    "boton": {"BackFillStyle": "Solid", "BackColor": "233, 232, 232", "ForeColor": "0, 0, 0"},
    "campo_es": {"BackColor": "255, 255, 255", "ForeColor": "0, 0, 0", "BorderWidth": "1"},
    "campo_simbolico": {"BackColor": "255, 255, 255", "ForeColor": "0, 0, 0", "BorderWidth": "1"},
    # DisplaySystemTime=true: muestra la hora del panel (sin tag de proceso; si no, TIA avisa "process tag missing").
    "fecha_hora": {"BackColor": "255, 255, 255", "ForeColor": "0, 0, 0", "BorderWidth": "0", "Mode": "Output",
                   "BackFillStyle": "Transparent", "DisplaySystemTime": "true"},
    "circulo": {"BackColor": "128, 128, 128"},
    "texto": {"BackFillStyle": "Transparent", "ForeColor": "0, 0, 0"},
}
_FUNCIONES_CON_TAG = ("SetBit", "ResetBit", "InvertBit")
_LONGITUD_TIPO = {"Bool": 1, "Byte": 1, "Char": 1, "Int": 2, "UInt": 2, "Word": 2, "DInt": 4, "UDInt": 4,
                  "DWord": 4, "Real": 4, "LReal": 8, "Time": 4}


class EspecificacionHmiInvalida(ValueError):
    """La especificación JSON de una pantalla/tabla HMI no es válida (mensaje en español)."""


# --------------------------------------------------------------------------- pantallas
def pantalla_xml(especificacion: dict, culturas: tuple[str, ...] = CULTURAS_POR_DEFECTO) -> str:
    nombre = _requerido(especificacion, "nombre", "pantalla")
    pantalla = copy.deepcopy(_prototipo("Screen"))
    attrs = pantalla.find("AttributeList")
    _poner(attrs, "Name", nombre)
    _poner(attrs, "Number", str(especificacion.get("numero", 1)))
    _poner(attrs, "BackColor", _color(especificacion.get("fondo", "0, 0, 0")))
    _ajustar_textos_culturas(pantalla, culturas)
    capa = pantalla.find("ObjectList/Hmi.Screen.ScreenLayer/ObjectList")
    nombres_usados: set[str] = set()
    for i, spec in enumerate(especificacion.get("objetos", []), start=1):
        capa.append(_objeto(spec, i, nombres_usados, culturas))
    return _documento(pantalla)


def _objeto(spec: dict, indice: int, usados: set[str], culturas) -> etree._Element:
    tipo = spec.get("tipo")
    if tipo not in TIPOS:
        raise EspecificacionHmiInvalida(f"Objeto {indice}: tipo '{tipo}' no soportado. Tipos: {', '.join(TIPOS)}.")
    obj = copy.deepcopy(_prototipo(TIPOS[tipo]))
    attrs = obj.find("AttributeList")
    nombre = spec.get("nombre") or f"{TIPOS[tipo]}_{indice}"
    if nombre in usados:
        raise EspecificacionHmiInvalida(f"Nombre de objeto repetido en la pantalla: '{nombre}'.")
    usados.add(nombre)
    _poner(attrs, "ObjectName", nombre)
    for atributo, valor in _POR_DEFECTO.get(tipo, {}).items():
        _poner(attrs, atributo, valor, solo_si_existe=True)
    _geometria(attrs, spec, tipo)
    _colores_y_bordes(attrs, spec, tipo)
    lista = obj.find("ObjectList")
    if lista is None:
        lista = etree.SubElement(obj, "ObjectList")
    _ajustar_textos_culturas(obj, culturas)
    _ajustar_fuente(lista, spec.get("fuente"), culturas)
    if "texto" in spec:
        _poner_texto(lista, tipo, str(spec["texto"]), culturas)
        if tipo == "boton":
            _poner(attrs, "Mode", "Text")
    # orden de TIA: animaciones, eventos, fuente/textos, propiedades
    animaciones = _animaciones(spec)
    eventos = _eventos(spec)
    for posicion, nodo in enumerate(animaciones + eventos):
        lista.insert(posicion, nodo)
    _campos(obj, attrs, lista, spec, tipo, nombre)
    if len(lista) == 0:
        obj.remove(lista)
    return obj


def _campos(obj, attrs, lista, spec: dict, tipo: str, nombre: str) -> None:
    """Propiedades propias de campos E/S, simbólicos y de fecha/hora."""
    if tipo in ("campo_es", "campo_simbolico"):
        lista.append(_propiedad_valor(_requerido(spec, "tag", f"objeto '{nombre}'")))
        _poner(attrs, "Mode", {"salida": "Output", "entrada": "Input", "entrada_salida": "InOutput"}
               .get(spec.get("modo", "salida"), spec.get("modo", "Output")))
        if tipo == "campo_es" and "formato" in spec:
            _poner(attrs, "FormatPattern", str(spec["formato"]))
            _poner(attrs, "FieldLength", str(len(str(spec["formato"]))))
    if tipo == "campo_simbolico":
        _enlace(obj, "TextList", _requerido(spec, "lista", f"objeto '{nombre}'"))
    if tipo == "fecha_hora":
        _poner(attrs, "ShowDate", _bool(spec.get("fecha", True)))
        _poner(attrs, "ShowTime", _bool(spec.get("hora", True)))


def _geometria(attrs, spec: dict, tipo: str) -> None:
    if tipo == "linea":
        _geometria_linea(attrs, spec)
        return
    for clave, atributo in (("x", "Left"), ("y", "Top"), ("ancho", "Width"), ("alto", "Height")):
        if clave in spec:
            _poner(attrs, atributo, str(int(spec[clave])))
    if tipo == "circulo":
        _poner(attrs, "Radius", str(int(spec.get("radio", min(spec.get("ancho", 33), spec.get("alto", 33)) // 2))))


def _geometria_linea(attrs, spec: dict) -> None:
    try:
        x1, y1, x2, y2 = (int(spec[k]) for k in ("x1", "y1", "x2", "y2"))
    except KeyError as e:
        raise EspecificacionHmiInvalida(f"Una línea necesita x1, y1, x2, y2 (falta {e}).") from e
    for nombre, valor in (("StartLeft", x1), ("StartTop", y1), ("EndLeft", x2), ("EndTop", y2),
                          ("Left", min(x1, x2)), ("Top", min(y1, y2)),
                          ("Width", abs(x2 - x1)), ("Height", abs(y2 - y1))):
        _poner(attrs, nombre, str(valor))
    if "color" in spec:
        _poner(attrs, "Color", _color(spec["color"]))
    if "grosor" in spec:
        _poner(attrs, "LineWidth", str(int(spec["grosor"])))


def _colores_y_bordes(attrs, spec: dict, tipo: str) -> None:
    if "fondo" in spec:
        _poner(attrs, "BackColor", _color(spec["fondo"]))
        _poner(attrs, "BackFillStyle", "Solid", solo_si_existe=True)
    if spec.get("transparente"):
        _poner(attrs, "BackFillStyle", "Transparent", solo_si_existe=True)
    if "color" in spec and tipo != "linea":
        _poner(attrs, "ForeColor", _color(spec["color"]), solo_si_existe=True)
    if "borde" in spec:
        _poner(attrs, "BorderColor", _color(spec["borde"]), solo_si_existe=True)
    if "grosor_borde" in spec:
        _poner(attrs, "BorderWidth", str(int(spec["grosor_borde"])), solo_si_existe=True)
    if "radio_esquina" in spec:
        _poner(attrs, "CornerRadius", str(int(spec["radio_esquina"])), solo_si_existe=True)
    if "alineacion" in spec:
        _poner(attrs, "HorizontalAlignment",
               {"izquierda": "Left", "centro": "Center", "derecha": "Right"}.get(spec["alineacion"],
                                                                                spec["alineacion"]),
               solo_si_existe=True)
    if tipo == "boton":
        # Sin degradado: color plano (diseño moderno).
        for nombre in ("UseFirstGradient", "UseSecondGradient"):
            _poner(attrs, nombre, "false", solo_si_existe=True)


def _ajustar_fuente(lista, fuente: dict | None, culturas) -> None:
    contenedor = next((h for h in lista if h.tag == "Hmi.Globalization.MultiLingualFont"), None)
    if contenedor is None:
        return
    items = contenedor.find("ObjectList")
    base = items[0]
    for h in list(items):
        items.remove(h)
    for cultura in culturas:
        item = copy.deepcopy(base)
        a = item.find("AttributeList")
        _poner(a, "Culture", cultura)
        _poner(a, "FontFamily", (fuente or {}).get("familia", FUENTE_POR_DEFECTO))
        if fuente and "tamano" in fuente:
            _poner(a, "FontSize", str(int(fuente["tamano"])))
        if fuente and "estilo" in fuente:
            _poner(a, "FontStyle", fuente["estilo"])
        items.append(item)


def _poner_texto(lista, tipo: str, texto: str, culturas) -> None:
    composiciones = ("TextOff", "TextOn") if tipo == "boton" else ("Text",)
    for mt in lista.findall("MultilingualText"):
        if mt.get("CompositionName") in composiciones:
            for item in mt.iter("MultilingualTextItem"):
                nodo = item.find("AttributeList/Text")
                _texto_formateado(nodo, texto)


def _texto_formateado(nodo, texto: str) -> None:
    for h in list(nodo):
        nodo.remove(h)
    nodo.text = None
    body = etree.SubElement(nodo, "body")
    p = etree.SubElement(body, "p")
    p.text = texto


def _ajustar_textos_culturas(elemento, culturas) -> None:
    """Cada MultilingualText del objeto (no de sus hijos objetos) tendrá un item por cultura."""
    for mt in elemento.iter("MultilingualText"):
        items = mt.find("ObjectList")
        if items is None or len(items) == 0:
            continue
        base = items[0]
        for h in list(items):
            items.remove(h)
        for cultura in culturas:
            item = copy.deepcopy(base)
            _poner(item.find("AttributeList"), "Culture", cultura)
            items.append(item)


# --------------------------------------------------------------------------- eventos y animaciones
def _eventos(spec: dict) -> list:
    resultado = []
    for clave, nombre_evento in _EVENTOS.items():
        acciones = spec.get(clave)
        if not acciones:
            continue
        evento = etree.Element("Hmi.Event.Event", ID="0", CompositionName="Events")
        _attrs(evento, Name=nombre_evento)
        manejador = etree.SubElement(etree.SubElement(evento, "ObjectList"), "Hmi.Event.FunctionListEventHandler",
                                     ID="0", CompositionName="EventHandler")
        entradas = etree.SubElement(manejador, "ObjectList")
        for accion in acciones:
            entradas.append(_funcion(accion))
        resultado.append(evento)
    return resultado


def _funcion(accion) -> etree._Element:
    if isinstance(accion, str) or not accion:
        raise EspecificacionHmiInvalida(f"Acción no válida: {accion!r}. Usa [\"SetBit\", \"Tag\"].")
    nombre, *args = accion
    entrada = etree.Element("Hmi.Event.FunctionListEntry", ID="0", CompositionName="FunctionListEntries")
    _attrs(entrada, Name=nombre, Type="SystemFunction")
    params = etree.SubElement(entrada, "ObjectList")
    if nombre in _FUNCIONES_CON_TAG:
        params.append(_parametro_enlace("Tag", _arg(args, 0, nombre)))
    elif nombre == "ActivateScreen":
        params.append(_parametro_enlace("Screen name", _arg(args, 0, nombre)))
        params.append(_parametro_valor("Object number", "System.Int32", str(int(args[1]) if len(args) > 1 else 0)))
    elif nombre == "SetTag":
        params.append(_parametro_enlace("Tag", _arg(args, 0, nombre)))
        params.append(_parametro_valor("Value", "System.Double", str(_arg(args, 1, nombre))))
    else:
        raise EspecificacionHmiInvalida(
            f"Función '{nombre}' no soportada todavía. Disponibles: SetBit, ResetBit, InvertBit, ActivateScreen, "
            f"SetTag.")
    return entrada


def _parametro_enlace(nombre: str, destino: str) -> etree._Element:
    p = etree.Element("Hmi.Event.FunctionListEntryParameter", ID="0", CompositionName="Parameters")
    _attrs(p, Name=nombre)
    valor = etree.SubElement(etree.SubElement(p, "LinkList"), "Value", TargetID="@OpenLink")
    etree.SubElement(valor, "Name").text = destino
    return p


def _parametro_valor(nombre: str, tipo: str, valor: str) -> etree._Element:
    p = etree.Element("Hmi.Event.FunctionListEntryParameter", ID="0", CompositionName="Parameters")
    a = _attrs(p, Name=nombre)
    etree.SubElement(a, "Value", Type=tipo).text = valor
    return p


def _animaciones(spec: dict) -> list:
    resultado = []
    if "apariencia" in spec:
        ap = spec["apariencia"]
        anim = etree.Element("Hmi.Dynamic.RangeAppearanceAnimation", ID="0", CompositionName="Animations")
        _attrs(anim, Name="RangeAppearanceAnimation")
        lista = etree.SubElement(anim, "ObjectList")
        lista.append(_disparador("RangeTag", _requerido(ap, "tag", "apariencia")))
        for rango in ap.get("rangos", []):
            valor, fondo, *resto = rango
            r = etree.SubElement(lista, "Hmi.Dynamic.Range", ID="0", CompositionName="RangeValues")
            texto = resto[0] if resto else fondo
            _attrs(r, BackColor=_color(fondo), FlashingType="Yes" if spec.get("parpadeo_en") == valor else "No",
                   ForeColor=_color(texto), LowerLimit=str(valor), UpperLimit=str(valor))
        resultado.append(anim)
    if "visible_si" in spec:
        vis = spec["visible_si"]
        anim = etree.Element("Hmi.Dynamic.VisibilityAnimation", ID="0", CompositionName="Animations")
        _attrs(anim, Name="VisibilityAnimation", RangeEnd=str(vis.get("hasta", 1)),
               RangeStart=str(vis.get("desde", 1)), Visible=_bool(vis.get("visible", True)))
        etree.SubElement(anim, "ObjectList").append(
            _disparador("VisibilityTag", _requerido(vis, "tag", "visible_si")))
        resultado.append(anim)
    return resultado


def _disparador(composicion: str, tag: str) -> etree._Element:
    d = etree.Element("Hmi.Dynamic.TagElementTrigger", ID="0", CompositionName=composicion)
    enlace = etree.SubElement(etree.SubElement(d, "LinkList"), "Tag", TargetID="@OpenLink")
    etree.SubElement(enlace, "Name").text = tag
    return d


def _propiedad_valor(tag: str) -> etree._Element:
    prop = etree.Element("Hmi.Screen.Property", ID="0", CompositionName="Properties")
    _attrs(prop, Name="ProcessValue")
    dinamico = etree.SubElement(etree.SubElement(prop, "ObjectList"), "Hmi.Dynamic.TagConnectionDynamic",
                                ID="0", CompositionName="Dynamic")
    _attrs(dinamico, Indirect="false")
    enlace = etree.SubElement(etree.SubElement(dinamico, "LinkList"), "Tag", TargetID="@OpenLink")
    etree.SubElement(enlace, "Name").text = tag
    return prop


# --------------------------------------------------------------------------- tags HMI
def tabla_tags_xml(nombre: str, tags: list[dict], culturas: tuple[str, ...] = CULTURAS_POR_DEFECTO) -> str:
    """tags: [{"nombre", "tipo"="Bool", "conexion"=None, "tag_plc"=None, "ciclo"="100 ms", "comentario"=""}].

    Con `conexion` + `tag_plc` el tag es externo (acceso simbólico, la conexión debe existir en el proyecto);
    sin ellos es interno.
    """
    tabla = etree.Element("Hmi.Tag.TagTable", ID="0")
    _attrs(tabla, Name=nombre)
    lista = etree.SubElement(tabla, "ObjectList")
    vistos = set()
    for t in tags:
        nombre_tag = _requerido(t, "nombre", "tag HMI")
        if nombre_tag in vistos:
            raise EspecificacionHmiInvalida(f"Tag HMI repetido: {nombre_tag}")
        vistos.add(nombre_tag)
        lista.append(_tag(t, culturas))
    return _documento(tabla)


def _tag(t: dict, culturas) -> etree._Element:
    tipo = t.get("tipo", "Bool")
    if tipo not in _LONGITUD_TIPO:
        raise EspecificacionHmiInvalida(f"Tipo de tag HMI no soportado: {tipo}. Usa: {', '.join(_LONGITUD_TIPO)}.")
    tag = etree.Element("Hmi.Tag.Tag", ID="0", CompositionName="Tags")
    _attrs(tag, AcquisitionTriggerMode="Visible", AddressAccessMode="Symbolic", Coding="Binary",
           ConfirmationType="None", GmpRelevant="false", JobNumber="0", Length=str(_LONGITUD_TIPO[tipo]),
           LinearScaling="false", LogicalAddress="", MandatoryCommenting="false", Name=t["nombre"],
           Persistency="false", QualityCode="false", ScalingHmiHigh="100", ScalingHmiLow="0",
           ScalingPlcHigh="10", ScalingPlcLow="0", StartValue="", SubstituteValue="",
           SubstituteValueUsage="None", Synchronization="false", UpdateMode="ProjectWide",
           UseMultiplexing="false")
    enlaces = etree.SubElement(tag, "LinkList")
    _enlace_simple(enlaces, "AcquisitionCycle", t.get("ciclo", "100 ms"))
    if t.get("conexion"):
        _enlace_simple(enlaces, "Connection", t["conexion"])
        _enlace_simple(enlaces, "ControllerTag", _requerido(t, "tag_plc", f"tag {t['nombre']}"))
    _enlace_simple(enlaces, "DataType", tipo)
    _enlace_simple(enlaces, "HmiDataType", tipo)
    objetos = etree.SubElement(tag, "ObjectList")
    for composicion, texto in (("Comment", t.get("comentario", "")), ("DisplayName", ""), ("TagValue", "")):
        objetos.append(_multilingue(composicion, texto, culturas, formateado=False))
    return tag


# --------------------------------------------------------------------------- listas de textos
def lista_textos_xml(nombre: str, entradas: dict | list, culturas: tuple[str, ...] = CULTURAS_POR_DEFECTO,
                     comentario: str = "") -> str:
    """entradas: {valor: texto} (o lista de [valor, texto]) para un campo simbólico."""
    pares = list(entradas.items()) if isinstance(entradas, dict) else [tuple(e) for e in entradas]
    lista = etree.Element("Hmi.TextGraphicList.TextList", ID="0")
    _attrs(lista, ListRange="Decimal", Name=nombre)
    objetos = etree.SubElement(lista, "ObjectList")
    objetos.append(_multilingue("Comment", comentario, culturas, formateado=False))
    for valor, texto in pares:
        entrada = etree.SubElement(objetos, "Hmi.TextGraphicList.TextListEntry", ID="0", CompositionName="Entries")
        _attrs(entrada, DefaultEntry="false", EntryType="SingleValue", From=str(int(valor)), To=str(int(valor)))
        etree.SubElement(entrada, "ObjectList").append(_multilingue("Text", str(texto), culturas, formateado=True))
    return _documento(lista)


# --------------------------------------------------------------------------- utilidades
@cache
def _prototipo_texto(nombre: str) -> bytes:
    archivo = DIR_PROTOTIPOS / f"{nombre}.xml"
    if not archivo.exists():
        raise EspecificacionHmiInvalida(f"Falta el prototipo {archivo.name}; ejecuta scripts/extraer_prototipos_hmi.py")
    return archivo.read_bytes()


def _prototipo(nombre: str) -> etree._Element:
    return etree.fromstring(_prototipo_texto(nombre), etree.XMLParser(remove_blank_text=True))


def _multilingue(composicion: str, texto: str, culturas, formateado: bool) -> etree._Element:
    mt = etree.Element("MultilingualText", ID="0", CompositionName=composicion)
    items = etree.SubElement(mt, "ObjectList")
    for cultura in culturas:
        item = etree.SubElement(items, "MultilingualTextItem", ID="0", CompositionName="Items")
        a = _attrs(item, Culture=cultura)
        nodo = etree.SubElement(a, "Text")
        if formateado and texto:
            _texto_formateado(nodo, texto)
        elif texto:
            nodo.text = texto
    return mt


def _documento(raiz: etree._Element) -> str:
    doc = etree.Element("Document")
    etree.SubElement(doc, "Engineering", version="V17")
    doc.append(raiz)
    for i, e in enumerate(e for e in doc.iter() if e.get("ID") is not None):
        e.set("ID", format(i, "X"))  # TIA usa IDs hexadecimales únicos por documento
    # Sin pretty_print: indentaría el interior de <Text><body><p> y el panel mostraría saltos y espacios.
    return etree.tostring(doc, xml_declaration=True, encoding="utf-8").decode("utf-8")


def _attrs(elemento, **valores) -> etree._Element:
    a = elemento.find("AttributeList")
    if a is None:
        a = etree.Element("AttributeList")
        elemento.insert(0, a)
    for nombre, valor in valores.items():
        etree.SubElement(a, nombre).text = valor if valor != "" else None
    return a


def _poner(attrs, nombre: str, valor: str, solo_si_existe: bool = False) -> None:
    nodo = attrs.find(nombre)
    if nodo is None:
        if solo_si_existe:
            return
        nodo = etree.SubElement(attrs, nombre)
        # TIA exporta los atributos en orden alfabético; se mantiene para que el import sea predecible.
        hermanos = sorted(attrs, key=lambda e: e.tag)
        for h in list(attrs):
            attrs.remove(h)
        attrs.extend(hermanos)
    nodo.text = valor


def _enlace(objeto, nombre: str, destino: str) -> None:
    enlaces = objeto.find("LinkList")
    if enlaces is None:
        enlaces = etree.Element("LinkList")
        objeto.insert(1, enlaces)  # después de AttributeList
    _enlace_simple(enlaces, nombre, destino)


def _enlace_simple(padre, nombre: str, destino: str) -> None:
    e = etree.SubElement(padre, nombre, TargetID="@OpenLink")
    etree.SubElement(e, "Name").text = destino


def _color(valor) -> str:
    if isinstance(valor, (list, tuple)):
        partes = [int(v) for v in valor]
    else:
        partes = [int(p) for p in str(valor).replace(";", ",").split(",")]
    if len(partes) != 3 or any(not 0 <= p <= 255 for p in partes):
        raise EspecificacionHmiInvalida(f"Color no válido: {valor!r}. Usa 'R, G, B' (0-255).")
    return ", ".join(str(p) for p in partes)


def _bool(valor) -> str:
    return "true" if valor else "false"


def _arg(args: list, i: int, funcion: str):
    if len(args) <= i:
        raise EspecificacionHmiInvalida(f"A la función {funcion} le faltan argumentos.")
    return args[i]


def _requerido(d: dict, clave: str, que: str):
    if not d.get(clave) and d.get(clave) != 0:
        raise EspecificacionHmiInvalida(f"Falta `{clave}` en {que}.")
    return d[clave]
