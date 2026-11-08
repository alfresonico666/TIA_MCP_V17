"""Generador KOP: XML válido contra XSD V17 y lectura de ida y vuelta (generar → leer)."""
import pytest
from lxml import etree

from tia_mcp.errores import EntradaInvalida
from tia_mcp.simaticml.kop.desde_json import bloque_desde_json, nodo
from tia_mcp.simaticml.kop.generador import documento, flgnet
from tia_mcp.simaticml.lector import leer_bloque
from tia_mcp.simaticml.modelo import Acceso


def _red_json(logica, **extra) -> dict:
    datos = {"tipo": "FB", "nombre": "FB_Prueba", "numero": 5, "redes": [{"titulo": "R1", "logica": logica}]}
    datos.update(extra)
    return datos


def _generar_y_leer(datos, validador=None):
    xml = documento(bloque_desde_json(datos))
    if validador is not None:
        assert validador.errores(xml) == []
    return leer_bloque(xml)


def test_arranque_paro_valida_y_se_lee_como_logica(validador, arranque_paro_json):
    bloque = _generar_y_leer(arranque_paro_json, validador)
    assert bloque.nombre == "FB_ArranqueParo" and bloque.tipo == "FB" and bloque.lenguaje == "LAD"
    assert bloque.redes[0].sentencias == ["#Motor := (#Marcha OR #Motor) AND #Paro_NC AND #Termico_NC"]
    escritos = {u.operando for u in bloque.usos if u.acceso == Acceso.ESCRITURA}
    assert escritos == {"#Motor"}
    static = bloque.interfaz["Static"][0]
    assert (static.tipo, static.nombre) == ("TON_TIME", "T_Arranque")


def test_temporizador_multiinstancia(validador):
    logica = [{"contacto": "#Marcha"},
              {"caja": "TON", "instancia": "#T_Arranque", "entradas": {"PT": "T#5s"}, "salidas": {"ET": "#Tiempo"}},
              {"bobina": "#Motor"}]
    bloque = _generar_y_leer(_red_json(logica, interfaz={"Static": [{"nombre": "T_Arranque", "tipo": "TON_TIME"}]}),
                             validador)
    sentencias = bloque.redes[0].sentencias
    assert "#Motor := #T_Arranque.Q" in sentencias
    assert any(s.startswith("#T_Arranque TON(") and "IN:=#Marcha" in s and "PT:=T#5s" in s for s in sentencias)
    assert any(u.operando == "#T_Arranque" and u.acceso == Acceso.INSTANCIA for u in bloque.usos)


def test_pines_libres_de_cajas_van_a_opencon(validador):
    """TIA rechaza la importación si un pin de caja queda sin cablear (p. ej. ET de un TON)."""
    xml = flgnet(nodo([{"contacto": "#A"}, {"caja": "TON", "instancia": "#T", "entradas": {"PT": "T#1s"}}]))
    cables = etree.fromstring(xml.encode()).iter("{*}Wire")
    pines_abiertos = {w[0].get("Name") for w in cables if any(c.tag.endswith("OpenCon") for c in w)}
    assert pines_abiertos == {"ET", "Q"}  # ET sin usar y Q al final del escalón
    assert validador.errores(f"<Document>{xml}</Document>") == []


def test_comparador_contador_move_y_flanco(validador):
    logica = [
        {"flanco": "P", "operando": "#Sensor", "memoria": "#Sensor_Flanco"},
        {"caja": "CTU", "instancia": "#Contador", "entradas": {"R": "#Reset", "PV": "10"},
         "salidas": {"CV": "#Cuenta"}},
        {"comparar": ["#Cuenta", ">=", "10"], "tipo": "Int"},
        {"caja": "MOVE", "entradas": {"in": "0"}, "salidas": {"out1": "#Cuenta"}},
        {"set": "#Lleno"},
    ]
    bloque = _generar_y_leer(_red_json(logica), validador)
    texto = "\n".join(bloque.redes[0].sentencias)
    assert "P(#Sensor)" in texto and "#Cuenta >= 10" in texto and "S #Lleno" in texto
    escritos = {u.operando for u in bloque.usos if u.acceso == Acceso.ESCRITURA}
    assert {"#Sensor_Flanco", "#Cuenta", "#Lleno"} <= escritos


def test_llamada_a_fb_con_tipos_resueltos_por_interfaz(validador):
    def interfaz_de(bloque):
        assert bloque == "FB_ArranqueParo"
        return {"Marcha": ("Input", "Bool"), "Motor": ("Output", "Bool")}

    datos = {"tipo": "OB", "nombre": "Main", "numero": 1, "redes": [{"titulo": "Motor 1", "logica": {
        "llamar": "FB_ArranqueParo", "instancia": "DB_ArranqueParo",
        "parametros": {"Marcha": "\"Marcha\"", "Motor": "\"Motor\""}}}]}
    xml = documento(bloque_desde_json(datos, interfaz_de))
    assert validador.errores(xml) == []
    bloque = leer_bloque(xml)
    assert bloque.llamadas[0].bloque == "FB_ArranqueParo" and bloque.llamadas[0].instancia == '"DB_ArranqueParo"'
    assert any(u.operando == '"Motor"' and u.acceso == Acceso.ESCRITURA for u in bloque.usos)


def test_fc_lleva_ret_val(validador):
    bloque = _generar_y_leer(_red_json([{"contacto": "#A"}, {"bobina": "#B"}], tipo="FC",
                                       interfaz={"Input": [{"nombre": "A"}], "Output": [{"nombre": "B"}]}),
                             validador)
    assert bloque.interfaz["Return"][0].nombre == "Ret_Val"


@pytest.mark.parametrize("logica, mensaje", [
    ({"caja": "TON", "entradas": {"PT": "T#1s"}}, "necesita `instancia`"),
    ({"caja": "TON", "instancia": "#T", "entradas": {"XX": "1"}}, "desconocidas"),
    ({"paralelo": [{"bobina": "#A"}, {"contacto": "#B"}]}, "no pueden terminar en bobina"),
    ([{"bobina": "#A"}, {"contacto": "#B"}], "después de una bobina"),
    ({"caja": "NO_EXISTE"}, "no está en el catálogo"),
    ({"contacto": "#Vec[1]"}, "array"),
])
def test_errores_claros(logica, mensaje):
    with pytest.raises(EntradaInvalida, match=mensaje):
        flgnet(nodo(logica))
