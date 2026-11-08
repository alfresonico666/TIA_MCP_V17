"""Escritura de programa con red de seguridad: validar → respaldar → importar → compilar → (restaurar).

Flujo común para KOP (JSON), SCL (fuente) y XML (SimaticML): si la compilación falla y el
bloque ya existía, se restaura la versión anterior y se devuelven los errores para corregir.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from pathlib import Path

from ..errores import EntradaInvalida
from ..scl.verificacion import verificar
from ..simaticml.kop.desde_json import bloque_desde_json
from ..simaticml.kop.generador import NS_FLGNET_V17, NS_INTERFAZ_V17, documento
from ..simaticml.lector import leer_bloque
from ..simaticml.validador_xsd import ValidadorXsd
from . import bloques
from .compilacion import compilar
from .proyecto import cultura_edicion
from .sesion import SesionTia, ruta_proyecto

_NS_INTERFAZ = re.compile(r'xmlns="(http://www\.siemens\.com/automation/Openness/SW/Interface/v\d+)"')
_NOMBRE_EN_XML = re.compile(r"<Name>([^<]+)</Name>")
_PRIMER_OB_LIBRE = 123  # los OB nuevos de ciclo/alarma deben usar números libres >= 123 (o el fijo de su tipo)
_EXTENSIONES = {"TYPE": ".udt", "DATA_BLOCK": ".db"}


class Programador:
    def __init__(self, sesion: SesionTia) -> None:
        self._sesion = sesion
        self._validador = ValidadorXsd(sesion.config.dir_esquemas)
        self._ns_interfaz: dict[str, str] = {}

    # ------------------------------------------------------------------ KOP
    def crear_kop(self, plc, especificacion: dict, carpeta: str | None = None, compilar_despues: bool = True,
                  restaurar_si_falla: bool = True) -> str:
        datos = dict(especificacion)
        datos.setdefault("numero", self._numero_libre(plc, str(datos.get("tipo", "")).upper()))
        definicion = bloque_desde_json(datos, lambda nombre: self._parametros_de(plc, nombre))
        xml = documento(definicion, cultura_edicion(self._sesion.proyecto), self._namespace_interfaz(plc),
                        NS_FLGNET_V17)
        errores = self._validador.errores(xml)
        if errores:
            raise EntradaInvalida("El XML generado no cumple el esquema de TIA V17:\n" + "\n".join(errores))
        return self._importar(plc, [definicion.nombre], lambda archivo: bloques.importar_xml(
            self._sesion, plc, archivo, carpeta), xml, ".xml", compilar_despues, restaurar_si_falla)

    # ------------------------------------------------------------------ SCL
    def importar_scl(self, plc, codigo: str, carpeta: str | None = None, compilar_despues: bool = True,
                     restaurar_si_falla: bool = True) -> str:
        verificacion = verificar(codigo)
        if not verificacion.correcto:
            raise EntradaInvalida("El SCL tiene errores antes de importar:\n" + verificacion.resumen())
        nombres = [b.split(" ", 1)[1].strip('"') for b in verificacion.bloques]
        primera = verificacion.bloques[0].split(" ", 1)[0]
        informe = self._importar(plc, nombres, lambda archivo: bloques.importar_fuente(
            self._sesion, plc, archivo, carpeta), codigo, _EXTENSIONES.get(primera, ".scl"),
            compilar_despues, restaurar_si_falla)
        avisos = "\n".join(f"AVISO: {a}" for a in verificacion.advertencias)
        return f"{informe}\n{avisos}".strip()

    # ------------------------------------------------------------------ XML
    def importar_xml(self, plc, xml: str, carpeta: str | None = None, compilar_despues: bool = True,
                     restaurar_si_falla: bool = True) -> str:
        if "<FlgNet" in xml:
            errores = self._validador.errores(xml)
            if errores:
                raise EntradaInvalida("El XML no cumple el esquema de TIA V17:\n" + "\n".join(errores))
        nombres = _NOMBRE_EN_XML.findall(xml)[:1]
        return self._importar(plc, nombres, lambda archivo: bloques.importar_xml(
            self._sesion, plc, archivo, carpeta), xml, ".xml", compilar_despues, restaurar_si_falla)

    # ------------------------------------------------------------------ flujo común
    def _importar(self, plc, nombres: list[str], importar: Callable[[Path], list[str]], contenido: str,
                  extension: str, compilar_despues: bool, restaurar_si_falla: bool) -> str:
        archivo = self._escribir_temporal(contenido, extension)
        respaldo = bloques.RespaldoBloques(self._sesion, plc, nombres)
        try:
            creados = importar(archivo)
        except Exception:
            respaldo.descartar()
            raise
        finally:
            archivo.unlink(missing_ok=True)
        lineas = [f"Importado: {', '.join(creados) or ', '.join(nombres)}"
                  + (f" (sobrescribió: {', '.join(respaldo.respaldados)})" if respaldo.respaldados else "")]
        if not compilar_despues:
            respaldo.descartar()
            return "\n".join([*lineas, "Sin compilar (compilar_despues=false)."])
        resultado = compilar(self._sesion, plc)
        lineas.append(resultado.resumen())
        if not resultado.correcto and restaurar_si_falla and respaldo.respaldados:
            restaurados = respaldo.restaurar()
            lineas.append(f"RESTAURADO a la versión anterior: {', '.join(restaurados)}. Corrige los errores y "
                          f"vuelve a intentarlo.")
        elif not resultado.correcto:
            lineas.append("El bloque quedó en el proyecto con errores: corrígelos y vuelve a importarlo.")
        respaldo.descartar()
        return "\n".join(lineas)

    def _escribir_temporal(self, contenido: str, extension: str) -> Path:
        carpeta = self._sesion.config.dir_trabajo
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / f"importar_{uuid.uuid4().hex[:8]}{extension}"
        archivo.write_text(contenido, encoding="utf-8-sig" if extension != ".xml" else "utf-8")
        return archivo

    # ------------------------------------------------------------------ apoyo
    def _parametros_de(self, plc, nombre_bloque: str) -> dict[str, tuple[str, str]]:
        """Sección y tipo de cada parámetro del bloque llamado, leídos del propio TIA."""
        bloque = bloques.buscar(plc, nombre_bloque)
        leido = leer_bloque(bloques.xml_de(self._sesion, bloque))
        return {m.nombre: (seccion, m.tipo) for seccion in ("Input", "Output", "InOut")
                for m in leido.interfaz.get(seccion, [])}

    def _numero_libre(self, plc, tipo: str) -> int:
        usados = {b.numero for b in bloques.listar(plc) if _misma_familia(b.tipo, tipo)}
        numero = _PRIMER_OB_LIBRE if tipo == "OB" else 1
        while numero in usados:
            numero += 1
        return numero

    def _namespace_interfaz(self, plc) -> str:
        """Namespace de <Sections> que usa ESTE TIA: se lee de un bloque existente (una vez por proyecto)."""
        clave = str(ruta_proyecto(self._sesion.proyecto))
        if clave not in self._ns_interfaz:
            self._ns_interfaz[clave] = self._detectar_namespace(plc)
        return self._ns_interfaz[clave]

    def _detectar_namespace(self, plc) -> str:
        for bloque, _ in bloques.recorrer(plc):
            if bool(bloque.IsConsistent):
                coincidencia = _NS_INTERFAZ.search(bloques.xml_de(self._sesion, bloque))
                if coincidencia:
                    return coincidencia.group(1)
        return NS_INTERFAZ_V17


def _misma_familia(tipo_existente: str, tipo_nuevo: str) -> bool:
    if tipo_nuevo == "OB":
        return tipo_existente == "OB"
    if tipo_nuevo in ("FB", "FC"):
        return tipo_existente == tipo_nuevo
    return False
