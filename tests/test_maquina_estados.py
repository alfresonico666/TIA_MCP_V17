"""Máquinas de estados Moore/Mealy → KOP (validado contra XSD V17 y leído de vuelta) y SCL."""
from __future__ import annotations

import copy

import pytest

from tia_mcp.scl.verificacion import verificar
from tia_mcp.simaticml.estilos.maquina_estados import (
    MaquinaInvalida,
    a_kop,
    a_scl,
    diagrama_mermaid,
    leer_maquina,
)
from tia_mcp.simaticml.kop.desde_json import bloque_desde_json
from tia_mcp.simaticml.kop.generador import documento
from tia_mcp.simaticml.lector import leer_bloque

ENTRADAS = [{"nombre": n} for n in ("Marcha", "Paro", "Termico_OK", "Reset")]
SALIDAS = [{"nombre": n} for n in ("Motor", "Piloto_Marcha", "Piloto_Falla")]

MOORE = {
    "nombre": "FB_Motor_Moore", "estilo": "moore", "lenguaje": "kop", "numero": 2,
    "entradas": ENTRADAS, "salidas": SALIDAS, "inicial": "REPOSO",
    "estados": [
        {"nombre": "REPOSO", "valor": 0},
        {"nombre": "MARCHA", "valor": 10, "salidas": {"Motor": True, "Piloto_Marcha": True}},
        {"nombre": "FALLA", "valor": 90, "salidas": {"Piloto_Falla": True}},
    ],
    "transiciones": [
        {"desde": "*", "hacia": "FALLA", "si": ["NOT Termico_OK"]},
        {"desde": "REPOSO", "hacia": "MARCHA", "si": ["Marcha", "NOT Paro", "Termico_OK"]},
        {"desde": "MARCHA", "hacia": "REPOSO", "si": ["Paro"]},
        {"desde": "FALLA", "hacia": "REPOSO", "si": ["Reset", "Termico_OK"]},
    ],
}


def _mealy() -> dict:
    spec = copy.deepcopy(MOORE)
    spec.update(nombre="FB_Motor_Mealy", estilo="mealy")
    spec["estados"][1]["salidas"] = {"Motor": ["NOT Paro", "Termico_OK"], "Piloto_Marcha": True}
    return spec


def test_moore_kop_valido_y_legible(validador):
    m = leer_maquina(MOORE)
    xml = documento(bloque_desde_json(a_kop(m)))
    assert validador.errores(xml) == []
    bloque = leer_bloque(xml)
    textos = [s for r in bloque.redes for s in r.sentencias]
    assert "#Motor := #Estado_Actual == 10" in textos
    assert "#Piloto_Falla := #Estado_Actual == 90" in textos
    assert any("Move(" in s and "#Estado_Previo == 0 AND #Marcha AND NOT #Paro AND #Termico_OK" in s
               for s in textos)
    # "*" se expande a todos los estados salvo el destino
    assert sum(1 for r in bloque.redes if r.titulo.endswith("-> FALLA")) == 2


def test_prioridad_primera_transicion_gana_por_orden_inverso():
    redes = a_kop(leer_maquina(MOORE))["redes"]
    titulos = [r["titulo"] for r in redes]
    # FALLA (primera en la lista) se escribe al final → es la que manda en KOP
    assert titulos.index("REPOSO -> FALLA") > titulos.index("REPOSO -> MARCHA")


def test_moore_rechaza_salidas_con_condicion():
    spec = _mealy()
    spec["estilo"] = "moore"
    with pytest.raises(MaquinaInvalida, match="Moore"):
        leer_maquina(spec)


def test_mealy_kop_valido_salidas_antes_de_transiciones(validador):
    m = leer_maquina(_mealy())
    spec_kop = a_kop(m)
    xml = documento(bloque_desde_json(spec_kop))
    assert validador.errores(xml) == []
    titulos = [r["titulo"] for r in spec_kop["redes"]]
    assert titulos.index("Salida Motor") < titulos.index("Foto del estado al inicio del ciclo")
    textos = [s for r in leer_bloque(xml).redes for s in r.sentencias]
    assert "#Motor := #Estado_Actual == 10 AND NOT #Paro AND #Termico_OK" in textos


def test_scl_moore_y_mealy_pasan_la_verificacion():
    for spec in (MOORE, _mealy()):
        m = leer_maquina({**spec, "lenguaje": "scl"})
        codigo = a_scl(m)
        resultado = verificar(codigo)
        assert resultado.correcto, resultado.resumen()
        assert codigo.isascii()
        assert "CASE #Estado_Previo OF" in codigo
        assert "Estado_Actual : Int := 0;" in codigo
    assert "#Motor := (#Estado_Actual = 10 AND NOT #Paro AND #Termico_OK);" in a_scl(leer_maquina(_mealy()))


@pytest.mark.parametrize("cambio, mensaje", [
    ({"estilo": "harel"}, "estilo"),
    ({"inicial": "NO_EXISTE"}, "inicial"),
    ({"transiciones": [{"desde": "REPOSO", "hacia": "OTRO", "si": []}]}, "desconocido"),
    ({"transiciones": [{"desde": "REPOSO", "hacia": "MARCHA", "si": ["Pulsador"]}]}, "no es una entrada"),
    ({"salidas": [*SALIDAS, {"nombre": "Sirena"}]}, "Sirena"),
])
def test_especificaciones_invalidas(cambio, mensaje):
    with pytest.raises(MaquinaInvalida, match=mensaje):
        leer_maquina({**MOORE, **cambio})


def test_diagrama_mermaid():
    texto = diagrama_mermaid(leer_maquina(MOORE))
    assert texto.startswith("stateDiagram-v2")
    assert "[*] --> REPOSO" in texto
    assert "REPOSO --> MARCHA : Marcha Y NOT Paro Y Termico_OK" in texto
