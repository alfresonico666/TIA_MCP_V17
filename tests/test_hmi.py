"""Generador y lector HMI (Python puro, sin TIA)."""
from __future__ import annotations

import pytest
from lxml import etree
from PIL import Image

from tia_mcp.simaticml.hmi.generador import (
    EspecificacionHmiInvalida,
    lista_textos_xml,
    pantalla_xml,
    tabla_tags_xml,
)
from tia_mcp.simaticml.hmi.lector import leer_pantalla, leer_tabla_tags, pantalla_como_texto
from tia_mcp.simaticml.hmi.vista_previa import png_de_xml

PANTALLA = {
    "nombre": "Principal", "numero": 1, "fondo": "0, 0, 0",
    "objetos": [
        {"tipo": "rectangulo", "nombre": "Panel", "x": 127, "y": 0, "ancho": 353, "alto": 271,
         "fondo": "247, 243, 247"},
        {"tipo": "texto", "nombre": "Titulo", "x": 133, "y": 0, "ancho": 343, "alto": 48, "texto": "ARRANQUE",
         "fuente": {"tamano": 24, "estilo": "Bold"}},
        {"tipo": "boton", "nombre": "Btn_Marcha", "x": 140, "y": 180, "ancho": 100, "alto": 40, "texto": "MARCHA",
         "al_pulsar": [["SetBit", "Cmd_Marcha"]], "al_soltar": [["ResetBit", "Cmd_Marcha"]]},
        {"tipo": "boton", "nombre": "Nav", "x": 3, "y": 8, "ancho": 119, "alto": 38, "texto": "DIAG",
         "al_click": [["ActivateScreen", "Diagnostico"], ["SetTag", "Pantalla", 2]]},
        {"tipo": "circulo", "nombre": "Led", "x": 300, "y": 100, "ancho": 33, "alto": 33,
         "apariencia": {"tag": "Motor", "rangos": [[0, "51, 51, 51"], [1, "0, 255, 0"]]}},
        {"tipo": "campo_es", "nombre": "Estado", "tag": "Estado", "x": 300, "y": 150, "ancho": 60, "alto": 30,
         "formato": "999"},
        {"tipo": "campo_simbolico", "nombre": "Estilo", "tag": "Sel_Estilo", "lista": "Estilos", "x": 140, "y": 60,
         "ancho": 150, "alto": 30, "modo": "entrada_salida"},
        {"tipo": "fecha_hora", "nombre": "Reloj", "x": 395, "y": 0, "ancho": 85, "alto": 22},
        {"tipo": "linea", "nombre": "Separador", "x1": 147, "y1": 44, "x2": 434, "y2": 44,
         "visible_si": {"tag": "Motor", "desde": 1, "hasta": 1}},
    ],
}


def _por_nombre(pantalla):
    return {o.nombre: o for o in pantalla.objetos}


def test_pantalla_ida_y_vuelta():
    xml = pantalla_xml(PANTALLA, culturas=("es-MX", "en-US"))
    p = leer_pantalla(xml)
    assert (p.nombre, p.numero, p.ancho, p.alto, p.fondo) == ("Principal", "1", 480, 272, "0, 0, 0")
    objetos = _por_nombre(p)
    assert set(objetos) == {o["nombre"] for o in PANTALLA["objetos"]}
    assert (objetos["Panel"].x, objetos["Panel"].y, objetos["Panel"].ancho) == (127, 0, 353)
    assert objetos["Titulo"].texto == "ARRANQUE"
    assert "24" in objetos["Titulo"].fuente
    eventos = {e.nombre: e.funciones for e in objetos["Btn_Marcha"].eventos}
    assert eventos == {"Press": ["SetBit(Cmd_Marcha)"], "Release": ["ResetBit(Cmd_Marcha)"]}
    assert objetos["Nav"].eventos[0].funciones == ["ActivateScreen(Diagnostico, 0)", "SetTag(Pantalla, 2)"]
    assert objetos["Led"].animaciones[0].startswith("RangeAppearance(Motor)")
    assert "<FlashingType>No</FlashingType>" in xml
    assert objetos["Separador"].animaciones == ["Visibility(Motor)"]
    assert "TextList=Estilos" in objetos["Estilo"].tags
    assert objetos["Estilo"].atributos["Mode"] == "InOutput"
    assert objetos["Estado"].atributos["FormatPattern"] == "999"
    assert "Principal" in pantalla_como_texto(p)


def test_ids_hexadecimales_unicos_y_textos_por_cultura():
    xml = pantalla_xml(PANTALLA, culturas=("es-MX", "en-US"))
    doc = etree.fromstring(xml.encode("utf-8"))
    ids = [e.get("ID") for e in doc.iter() if e.get("ID") is not None]
    assert len(ids) == len(set(ids))
    assert all(int(i, 16) >= 0 for i in ids)
    titulo = next(o for o in doc.iter("Hmi.Screen.TextField"))
    culturas = [c.text for c in titulo.iter("Culture")]
    assert culturas.count("es-MX") == culturas.count("en-US") > 0


def test_texto_formateado_sin_espacios_extra():
    """TIA muestra literalmente lo que hay en <body><p>: no debe haber saltos de línea añadidos."""
    xml = pantalla_xml({"nombre": "P", "objetos": [{"tipo": "texto", "nombre": "T", "texto": "HOLA"}]})
    assert "<body><p>HOLA</p></body>" in xml


def test_lineas_usan_coordenadas_de_inicio_y_fin():
    xml = pantalla_xml({"nombre": "P", "objetos": [{"tipo": "linea", "x1": 10, "y1": 20, "x2": 110, "y2": 20}]})
    attrs = etree.fromstring(xml.encode()).find(".//Hmi.Screen.Line/AttributeList")
    valores = {e.tag: e.text for e in attrs}
    assert (valores["StartLeft"], valores["EndLeft"], valores["Width"]) == ("10", "110", "100")


@pytest.mark.parametrize("objeto, mensaje", [
    ({"tipo": "pulsador"}, "no soportado"),
    ({"tipo": "boton", "fondo": "300, 0, 0"}, "Color no válido"),
    ({"tipo": "boton", "al_click": [["Logoff"]]}, "no soportada"),
    ({"tipo": "campo_es"}, "Falta `tag`"),
])
def test_especificaciones_invalidas(objeto, mensaje):
    with pytest.raises(EspecificacionHmiInvalida, match=mensaje):
        pantalla_xml({"nombre": "P", "objetos": [objeto]})


def test_nombres_repetidos_se_rechazan():
    with pytest.raises(EspecificacionHmiInvalida, match="repetido"):
        pantalla_xml({"nombre": "P", "objetos": [{"tipo": "texto", "nombre": "A"}, {"tipo": "texto", "nombre": "A"}]})


def test_tabla_tags_externos_e_internos():
    xml = tabla_tags_xml("HMI_Motor", [
        {"nombre": "Cmd_Marcha", "conexion": "HMI_Connection_1", "tag_plc": "DB_HMI.Cmd_Marcha"},
        {"nombre": "Estado", "tipo": "Int", "conexion": "HMI_Connection_1", "tag_plc": "DB_HMI.Estado"},
        {"nombre": "Interno", "tipo": "Int"},
    ])
    nombre, tags = leer_tabla_tags(xml)
    assert nombre == "HMI_Motor"
    por_nombre = {t.nombre: t for t in tags}
    assert por_nombre["Cmd_Marcha"].tag_plc == "DB_HMI.Cmd_Marcha"
    assert por_nombre["Interno"].conexion == ""
    longitudes = {t.findtext("AttributeList/Name"): t.findtext("AttributeList/Length")
                  for t in etree.fromstring(xml.encode()).iter("Hmi.Tag.Tag")}
    assert longitudes == {"Cmd_Marcha": "1", "Estado": "2", "Interno": "2"}


def test_tag_externo_sin_tag_plc_falla():
    with pytest.raises(EspecificacionHmiInvalida, match="tag_plc"):
        tabla_tags_xml("T", [{"nombre": "X", "conexion": "HMI_Connection_1"}])


def test_lista_textos():
    xml = lista_textos_xml("Estilos", {"1": "Banderas", "2": "Moore", "3": "Mealy"}, culturas=("es-MX",))
    doc = etree.fromstring(xml.encode())
    entradas = doc.findall(".//Hmi.TextGraphicList.TextListEntry")
    assert [e.findtext("AttributeList/From") for e in entradas] == ["1", "2", "3"]
    assert ["".join(e.find(".//Text").itertext()) for e in entradas] == ["Banderas", "Moore", "Mealy"]


def test_vista_previa_png(tmp_path):
    destino = png_de_xml(pantalla_xml(PANTALLA), tmp_path / "p.png", escala=1, estado=1)
    imagen = Image.open(destino)
    assert imagen.size == (480, 272)
    assert imagen.getpixel((316, 116)) == (0, 255, 0)  # círculo "Led" en estado 1 = verde
    assert imagen.getpixel((5, 5)) == (0, 0, 0)        # fondo negro
