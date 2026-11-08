"""Extrae PROTOTIPOS NEUTROS de objetos HMI (WinCC Basic/Comfort V17) desde una pantalla exportada.

Un prototipo es un objeto real exportado por TIA V17 al que se le quita todo lo del proyecto de origen
(nombre, textos, eventos, animaciones, enlaces a tags/imágenes/listas). Solo quedan los atributos que TIA
exige, con sus valores por defecto. El generador (`simaticml/hmi/generador.py`) los clona y les aplica la
especificación. Así cada formato está "copiado de un export real" (regla 6 del CLAUDE.md) sin incluir
datos de clientes en el repositorio.

Uso (una vez, o al soportar un objeto nuevo):
    .venv\\Scripts\\python scripts\\extraer_prototipos_hmi.py <carpeta_HMI_exportada>
    (la carpeta que crea tia_conocimiento aprender: ...\\_conocimiento_tia\\<proyecto>\\HMI\\<HMI_RT_x>)
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

from lxml import etree

DESTINO = Path(__file__).resolve().parents[1] / "src" / "tia_mcp" / "simaticml" / "hmi" / "prototipos"
TIPOS = ("Rectangle", "TextField", "Button", "Circle", "IOField", "SymbolicIOField", "DateTimeField", "Line")
QUITAR = ("Hmi.Event.Event", "Hmi.Screen.Property")


def neutralizar(objeto) -> etree._Element:
    o = copy.deepcopy(objeto)
    attrs = o.find("AttributeList")
    attrs.find("ObjectName").text = "PROTOTIPO"
    for nombre in ("Left", "Top"):
        if attrs.find(nombre) is not None:
            attrs.find(nombre).text = "0"
    enlaces = o.find("LinkList")
    if enlaces is not None:
        o.remove(enlaces)
    lista = o.find("ObjectList")
    if lista is not None:
        for hijo in list(lista):
            if hijo.tag in QUITAR or hijo.tag.startswith("Hmi.Dynamic."):
                lista.remove(hijo)
        for texto in lista.iter("Text"):
            for h in list(texto):
                texto.remove(h)
            texto.text = None
    return o


def esqueleto_pantalla(pantalla) -> etree._Element:
    s = copy.deepcopy(pantalla)
    attrs = s.find("AttributeList")
    attrs.find("Name").text = "PROTOTIPO"
    for capa in s.find("ObjectList").findall("Hmi.Screen.ScreenLayer"):
        objetos = capa.find("ObjectList")
        if objetos is not None:
            for h in list(objetos):
                objetos.remove(h)
    for tecla in s.find("ObjectList").findall("Hmi.Screen.SoftKey"):
        s.find("ObjectList").remove(tecla)
    for texto in s.iter("Text"):
        for h in list(texto):
            texto.remove(h)
        texto.text = None
    return s


def main(carpeta: Path) -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    encontrados: dict[str, etree._Element] = {}
    pantalla_base = None
    for archivo in sorted((carpeta / "pantallas").rglob("*.xml")) + sorted((carpeta / "plantillas").rglob("*.xml")):
        doc = etree.parse(str(archivo), etree.XMLParser(remove_blank_text=True))
        pantalla = doc.find(".//Hmi.Screen.Screen")
        if pantalla is not None and pantalla_base is None:
            pantalla_base = pantalla
        for tipo in TIPOS:
            if tipo not in encontrados:
                obj = doc.find(f".//Hmi.Screen.{tipo}")
                if obj is not None:
                    encontrados[tipo] = neutralizar(obj)
    for tipo, objeto in encontrados.items():
        (DESTINO / f"{tipo}.xml").write_bytes(etree.tostring(objeto, pretty_print=True, encoding="utf-8"))
        print(f"  prototipo {tipo}")
    if pantalla_base is not None:
        (DESTINO / "Screen.xml").write_bytes(
            etree.tostring(esqueleto_pantalla(pantalla_base), pretty_print=True, encoding="utf-8"))
        print("  esqueleto Screen")
    faltan = [t for t in TIPOS if t not in encontrados]
    if faltan:
        print(f"AVISO: no se encontraron: {', '.join(faltan)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
