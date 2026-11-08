"""Regresión: una red KOP con ramas compartidas no debe tardar tiempo exponencial (colgaba el servidor)."""
from __future__ import annotations

import time

from lxml import etree

from tia_mcp.simaticml.flgnet import MAX_LONGITUD_EXPRESION, RedFlgNet

NS = "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4"


def _red_diamantes(n: int) -> str:
    """n "diamantes" en cadena: cada uno = 2 contactos en paralelo (O) alimentados por la misma salida."""
    accesos, piezas, cables = [], [], []
    uid = 0

    def nuevo():
        nonlocal uid
        uid += 1
        return uid

    origen = "<Powerrail/>"
    for i in range(n):
        a, b, o = nuevo(), nuevo(), nuevo()
        for contacto in (a, b):
            acc = nuevo()
            accesos.append(f'<Access Scope="GlobalVariable" UId="{acc}"><Symbol><Component Name="S{i}_{contacto}"/>'
                           f"</Symbol></Access>")
            piezas.append(f'<Part Name="Contact" UId="{contacto}"/>')
            cables.append(f'<Wire UId="{nuevo()}"><IdentCon UId="{acc}"/><NameCon UId="{contacto}" Name="operand"/>'
                          f"</Wire>")
        piezas.append(f'<Part Name="O" UId="{o}"><TemplateValue Name="Card" Type="Cardinality">2'
                      f"</TemplateValue></Part>")
        cables.append(f'<Wire UId="{nuevo()}">{origen}<NameCon UId="{a}" Name="in"/><NameCon UId="{b}" Name="in"/>'
                      f"</Wire>")
        cables.append(f'<Wire UId="{nuevo()}"><NameCon UId="{a}" Name="out"/><NameCon UId="{o}" Name="in1"/></Wire>')
        cables.append(f'<Wire UId="{nuevo()}"><NameCon UId="{b}" Name="out"/><NameCon UId="{o}" Name="in2"/></Wire>')
        origen = f'<NameCon UId="{o}" Name="out"/>'
    bobina, acc = nuevo(), nuevo()
    accesos.append(f'<Access Scope="GlobalVariable" UId="{acc}"><Symbol><Component Name="Salida"/></Symbol></Access>')
    piezas.append(f'<Part Name="Coil" UId="{bobina}"/>')
    cables.append(f'<Wire UId="{nuevo()}">{origen}<NameCon UId="{bobina}" Name="in"/></Wire>')
    cables.append(f'<Wire UId="{nuevo()}"><IdentCon UId="{acc}"/><NameCon UId="{bobina}" Name="operand"/></Wire>')
    return (f'<FlgNet xmlns="{NS}"><Parts>{"".join(accesos)}{"".join(piezas)}</Parts>'
            f'<Wires>{"".join(cables)}</Wires></FlgNet>')


def test_red_con_ramas_compartidas_es_rapida_y_acotada():
    red = RedFlgNet(etree.fromstring(_red_diamantes(60).encode()), indice_red=1)
    inicio = time.perf_counter()
    sentencias = red.sentencias()
    assert time.perf_counter() - inicio < 2.0
    assert len(sentencias) == 1
    assert sentencias[0].startswith('"Salida" := ')
    assert len(sentencias[0]) < MAX_LONGITUD_EXPRESION + 100
