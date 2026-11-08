"""Vista previa PNG de una pantalla HMI (SimaticML generado o exportado de TIA), sin abrir TIA.

Sirve para revisar el diseño (posiciones, colores, textos, solapes) antes de importar, documentar el proyecto
y mostrárselo al usuario. Es una aproximación: los objetos animados se dibujan en el estado del primer rango
(`estado`=0 por defecto) o en el que se pida.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .lector import ObjetoHmi, PantallaHmi, leer_pantalla

_FUENTES = Path(r"C:\Windows\Fonts")


def png_de_xml(xml: str | bytes, destino: Path, escala: int = 2, estado: int | None = None) -> Path:
    return dibujar(leer_pantalla(xml), destino, escala, estado)


def dibujar(pantalla: PantallaHmi, destino: Path, escala: int = 2, estado: int | None = None) -> Path:
    ancho, alto = (pantalla.ancho or 480) * escala, (pantalla.alto or 272) * escala
    imagen = Image.new("RGB", (ancho, alto), _rgb(pantalla.fondo, (0, 0, 0)))
    lienzo = ImageDraw.Draw(imagen)
    for objeto in pantalla.objetos:  # orden de capa = orden en el XML
        _dibujar_objeto(lienzo, objeto, escala, estado)
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino)
    return destino


def _dibujar_objeto(d: ImageDraw.ImageDraw, o: ObjetoHmi, k: int, estado: int | None) -> None:
    c = o.crudos
    caja = (o.x * k, o.y * k, (o.x + o.ancho) * k, (o.y + o.alto) * k)
    fondo, texto_color = _colores(o, estado)
    transparente = c.get("BackFillStyle") == "Transparent"
    borde = _rgb(c.get("BorderColor"), None)
    grosor = int(c.get("BorderWidth") or 0) * k
    radio = int(c.get("CornerRadius") or c.get("RoundCornerWidth") or 0) * k
    if o.tipo == "Line":
        puntos = [int(c.get(n) or 0) * k for n in ("StartLeft", "StartTop", "EndLeft", "EndTop")]
        d.line(puntos, fill=_rgb(c.get("Color"), (255, 255, 255)), width=max(1, int(c.get("LineWidth") or 1) * k))
        return
    if o.tipo == "Circle":
        d.ellipse(caja, fill=None if transparente else fondo, outline=borde, width=max(grosor, 1 if borde else 0))
        return
    if o.tipo in ("Rectangle", "Button", "IOField", "SymbolicIOField", "DateTimeField", "TextField") and (
            not transparente or (grosor and borde)):
        d.rounded_rectangle(caja, radius=min(radio, (caja[3] - caja[1]) // 2),
                            fill=None if transparente else fondo,
                            outline=borde if grosor else None, width=grosor)
    contenido = _texto_a_mostrar(o)
    if contenido:
        fuente = _fuente(o.fuente, k)
        centrado = o.tipo == "Button" or c.get("HorizontalAlignment") == "Center"
        _texto(d, caja, contenido, fuente, texto_color, centrado, derecha=c.get("HorizontalAlignment") == "Right")


def _colores(o: ObjetoHmi, estado: int | None) -> tuple[tuple, tuple]:
    fondo = _rgb(o.crudos.get("BackColor"), (200, 200, 200))
    texto = _rgb(o.crudos.get("ForeColor"), (0, 0, 0))
    if o.rangos:
        elegido = next((r for r in o.rangos if estado is not None and r[0] == str(estado)), o.rangos[0])
        fondo = _rgb(elegido[1], fondo)
    return fondo, texto


def _texto_a_mostrar(o: ObjetoHmi) -> str:
    if o.tipo == "IOField":
        return "8" * max(1, len(o.crudos.get("FormatPattern", "999")))
    if o.tipo == "SymbolicIOField":
        lista = next((t.split("=", 1)[1] for t in o.tags if t.startswith("TextList=")), "lista")
        return f"[{lista}]"
    if o.tipo == "DateTimeField":
        fecha, hora = o.crudos.get("ShowDate") == "true", o.crudos.get("ShowTime") == "true"
        return " ".join(p for p, v in (("07/11/2026", fecha), ("12:00:00", hora)) if v)
    return o.texto.split(" / ")[0] if o.texto else ""


def _texto(d, caja, contenido: str, fuente, color, centrado: bool, derecha: bool = False) -> None:
    x0, y0, x1, y1 = caja
    lineas = contenido.split("\n")
    alturas = [d.textbbox((0, 0), linea or " ", font=fuente) for linea in lineas]
    alto_total = sum(b[3] - b[1] for b in alturas) + 2 * (len(lineas) - 1)
    y = y0 + (y1 - y0 - alto_total) / 2
    for linea, b in zip(lineas, alturas, strict=True):
        ancho = b[2] - b[0]
        x = x0 + (x1 - x0 - ancho) / 2 if centrado else (x1 - ancho - 4 if derecha else x0 + 4)
        d.text((x, y - b[1]), linea, font=fuente, fill=color)
        y += (b[3] - b[1]) + 2


def _fuente(descripcion: str, k: int):
    partes = descripcion.split()
    tamano = next((int(p) for p in partes if p.isdigit()), 13)
    negrita = "Bold" in descripcion
    archivo = _FUENTES / ("tahomabd.ttf" if negrita else "tahoma.ttf")
    try:
        # TIA usa puntos a 96 ppp: 1 pt ≈ 1.33 px
        return ImageFont.truetype(str(archivo), int(tamano * 1.33 * k * 0.75))
    except OSError:
        return ImageFont.load_default()


def _rgb(texto: str | None, por_defecto):
    try:
        partes = tuple(int(p) for p in str(texto).split(","))
        return partes if len(partes) == 3 else por_defecto
    except (TypeError, ValueError):
        return por_defecto
