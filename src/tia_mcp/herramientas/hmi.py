"""Herramienta `tia_hmi`: paneles HMI (KTP400/KTP700 Basic, Comfort) — pantallas, tags HMI, listas, compilar."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from .. import formato
from ..errores import EntradaInvalida
from ..openness import hmi
from ..simaticml.hmi import generador, vista_previa
from .contexto import ESCRITURA, Contexto, accion_desconocida, requerido

AYUDA_HMI = """Pantalla (crear_pantalla, `especificacion`):
{"nombre": "Principal", "numero": 1, "fondo": "0, 0, 0", "objetos": [OBJETO, ...]}
OBJETO (x, y, ancho, alto en píxeles; KTP400 = 480x272):
 {"tipo": "rectangulo", "fondo": "247, 243, 247", "borde": "24, 28, 49", "grosor_borde": 1}
 {"tipo": "texto", "texto": "TITULO", "fuente": {"tamano": 24, "estilo": "Bold, Italic"}, "color": "49, 52, 74",
  "alineacion": "izquierda|centro|derecha"}
 {"tipo": "boton", "nombre": "Btn_Marcha", "texto": "MARCHA", "fondo": "...", "color": "...", "borde": "...",
  "radio_esquina": 8, "al_pulsar": [["SetBit", "Cmd_Marcha"]], "al_soltar": [["ResetBit", "Cmd_Marcha"]],
  "al_click": [["ActivateScreen", "Diagnostico"], ["InvertBit", "X"], ["SetTag", "Pantalla", 2]]}
 {"tipo": "circulo", "apariencia": {"tag": "Motor", "rangos": [[0, "51, 51, 51"], [1, "0, 255, 0"]]},
  "parpadeo_en": 1}
 {"tipo": "campo_es", "tag": "Estado", "formato": "999", "modo": "salida|entrada|entrada_salida"}
 {"tipo": "campo_simbolico", "tag": "Sel_Estilo", "lista": "Estilos", "modo": "entrada_salida"}
 {"tipo": "fecha_hora", "fecha": true, "hora": true}
 {"tipo": "linea", "x1": 147, "y1": 44, "x2": 434, "y2": 44, "color": "255, 203, 0", "grosor": 3}
Cualquier objeto: "visible_si": {"tag": "X", "desde": 1, "hasta": 1, "visible": true}.
Tags (crear_tags): `nombre` de la tabla + `tags`: [{"nombre": "Cmd_Marcha", "tipo": "Bool|Int|Real|...",
 "conexion": "HMI_Connection_1", "tag_plc": "DB_HMI.Cmd_Marcha", "ciclo": "100 ms"}]  (sin conexión = interno)
Listas (crear_lista_textos): `nombre` + `entradas`: {"1": "Banderas", "2": "Moore"}.
Openness V17 NO crea la conexión HMI integrada ni elige la pantalla inicial: se hacen una vez a mano
(conectar_plc explica cómo); conviene partir de un proyecto/plantilla base que ya las tenga."""


def registrar(servidor: MCPServer, ctx: Contexto) -> None:
    acciones = ["paneles", "agregar_panel", "conectar_plc", "leer", "xml", "crear_pantalla", "crear_tags",
                "crear_lista_textos", "importar_xml", "compilar", "exportar", "vista_previa", "ayuda"]

    @servidor.tool(annotations=ESCRITURA)
    async def tia_hmi(action: Literal["paneles", "agregar_panel", "conectar_plc", "leer", "xml", "crear_pantalla",
                                      "crear_tags", "crear_lista_textos", "importar_xml", "compilar", "exportar",
                                      "vista_previa", "ayuda"],
                      panel: str | None = None, plc: str | None = None, nombre: str | None = None,
                      referencia: str | None = None,
                      tipo: Literal["pantalla", "plantilla", "tags", "lista_textos", "conexion"] | None = None,
                      especificacion: dict[str, Any] | None = None, tags: list[dict[str, Any]] | None = None,
                      entradas: dict[str, str] | None = None, xml: str | None = None,
                      carpeta: str | None = None, conexion_confirmada: bool = False) -> str:
        """Paneles HMI WinCC Basic/Comfort (p. ej. KTP400 Basic). `panel` opcional si hay uno solo.

        - paneles: paneles con sus pantallas, plantillas, tablas de tags y listas de textos.
        - agregar_panel: `nombre` + `referencia` con versión ('6AV2 123-2DB03-0AX0/17.0.0.0' = KTP400 Basic).
        - conectar_plc: `panel` + `plc` a la misma subred (+ instrucciones para la conexión HMI, que es manual).
        - leer: `tipo` (pantalla|plantilla|tags|lista_textos) + `nombre` → resumen legible (objetos, posición,
          colores, eventos, animaciones, tags). Úsalo para aprender diseños de proyectos anteriores.
        - xml: SimaticML crudo de ese objeto.
        - crear_pantalla: `especificacion` JSON (ver action='ayuda'); reemplaza si ya existe.
        - crear_tags: `nombre` (tabla) + `tags`. Si algún tag usa `conexion`, pasa `conexion_confirmada`=true
          SOLO si esa conexión HMI ya existe: importar tags con una conexión inexistente CIERRA TIA.
          crear_lista_textos: `nombre` + `entradas`.
        - importar_xml: `tipo` + `xml` (SimaticML HMI completo).
        - compilar: compila el panel y devuelve errores/advertencias.
        - exportar: todo el panel a `carpeta` (XML).
        - vista_previa: PNG de una pantalla en `carpeta`: desde `especificacion` (sin TIA) o desde la pantalla
          `nombre` del panel. Úsalo para revisar el diseño y para enseñárselo al usuario.
        - ayuda: formato de las especificaciones.
        """
        if action == "ayuda":
            return AYUDA_HMI
        if action == "vista_previa" and especificacion is not None:
            try:
                xml_spec = generador.pantalla_xml(especificacion)
            except generador.EspecificacionHmiInvalida as e:
                raise EntradaInvalida(str(e)) from e
            destino = Path(requerido(carpeta, "carpeta", action)).expanduser() / f"{especificacion['nombre']}.png"
            return f"Vista previa: {vista_previa.png_de_xml(xml_spec, destino)}"

        def ejecutar():
            s = ctx.sesion
            if action == "agregar_panel":
                ctx.exigir_escritura()
                return hmi.agregar_panel(s, requerido(nombre, "nombre", action),
                                         requerido(referencia, "referencia", action))
            if action == "conectar_plc":
                ctx.exigir_escritura()
                return hmi.conectar_a_plc(s, requerido(panel, "panel", action), requerido(plc, "plc", action))
            if action == "paneles":
                bloques = []
                for dispositivo, h in hmi.paneles(s):
                    c = hmi.contenido(h)
                    bloques.append(formato.secciones(
                        f"Panel {dispositivo.Name} (software {c.panel})",
                        formato.lineas("Pantallas", c.pantallas), formato.lineas("Plantillas", c.plantillas),
                        formato.lineas("Tablas de tags", c.tablas_tags),
                        formato.lineas("Listas de textos", c.listas_textos),
                        formato.lineas("Conexiones", c.conexiones)))
                return formato.secciones(*bloques) or "No hay paneles HMI en el proyecto."
            h = hmi.panel(s, panel)
            if action == "leer":
                return hmi.leer(s, h, requerido(tipo, "tipo", action), requerido(nombre, "nombre", action))
            if action == "xml":
                return hmi.xml_de(s, h, requerido(tipo, "tipo", action), requerido(nombre, "nombre", action))
            if action == "compilar":
                return hmi.compilar_panel(s, h).resumen()
            if action == "exportar":
                return "\n".join(hmi.exportar(s, h, Path(requerido(carpeta, "carpeta", action)).expanduser()))
            if action == "vista_previa":
                pantalla = requerido(nombre, "nombre", action)
                destino = Path(requerido(carpeta, "carpeta", action)).expanduser() / f"{pantalla}.png"
                return f"Vista previa: {vista_previa.png_de_xml(hmi.xml_de(s, h, 'pantalla', pantalla), destino)}"
            ctx.exigir_escritura()
            if action == "crear_tags" and any(t.get("conexion") for t in (tags or [])) and not conexion_confirmada:
                raise EntradaInvalida(
                    "Hay tags enlazados a una conexión HMI. Si la conexión no existe, TIA se CIERRA al importarlos "
                    "(comprobado en V17). Pregunta al usuario si ya creó la conexión (Dispositivos y redes → "
                    "Conexión HMI) y repite con conexion_confirmada=true; si no, crea los tags sin `conexion` "
                    "(internos) para previsualizar.")
            parametros = {"especificacion": especificacion, "nombre": nombre, "tags": tags, "entradas": entradas,
                          "xml": xml, "tipo": tipo}
            tipo_import, contenido = _xml_a_importar(action, parametros, hmi.culturas_proyecto(s), acciones)
            importados = hmi.importar(s, h, tipo_import, contenido)
            return f"Importado en {h.Name} ({tipo_import}): {', '.join(importados)}. Compila con action='compilar'."
        return await ctx.ejecutar(ejecutar)


def _xml_a_importar(action: str, p: dict, culturas: tuple[str, ...], acciones: list[str]) -> tuple[str, str]:
    """(tipo de importación, SimaticML) según la acción de escritura."""
    try:
        if action == "crear_pantalla":
            return "pantalla", generador.pantalla_xml(requerido(p["especificacion"], "especificacion", action),
                                                      culturas)
        if action == "crear_tags":
            return "tags", generador.tabla_tags_xml(requerido(p["nombre"], "nombre", action),
                                                    requerido(p["tags"], "tags", action), culturas)
        if action == "crear_lista_textos":
            return "lista_textos", generador.lista_textos_xml(requerido(p["nombre"], "nombre", action),
                                                              requerido(p["entradas"], "entradas", action), culturas)
        if action == "importar_xml":
            return requerido(p["tipo"], "tipo", action), requerido(p["xml"], "xml", action)
    except generador.EspecificacionHmiInvalida as e:
        raise EntradaInvalida(str(e)) from e
    raise accion_desconocida(action, acciones)
