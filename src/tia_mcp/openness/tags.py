"""Tablas de variables PLC: listar, leer, buscar, crear/actualizar y borrar."""
from __future__ import annotations

import difflib
from collections.abc import Iterator
from dataclasses import dataclass

from ..analisis.organizar_tags import REGLAS_SUGERIDAS, ReglaCategoria, planificar, resumen_plan
from ..errores import EntradaInvalida, NoEncontrado
from .compilacion import compilar
from .proyecto import cultura_edicion
from .sesion import SesionTia


@dataclass(frozen=True)
class TagLeido:
    nombre: str
    tipo: str
    direccion: str
    comentario: str
    tabla: str


def recorrer_tablas(plc) -> Iterator[tuple[object, str]]:
    yield from _recorrer_grupo(plc.TagTableGroup, "")


def _recorrer_grupo(grupo, carpeta: str) -> Iterator[tuple[object, str]]:
    for tabla in grupo.TagTables:
        yield tabla, carpeta
    for subgrupo in grupo.Groups:
        yield from _recorrer_grupo(subgrupo, f"{carpeta}/{subgrupo.Name}".lstrip("/"))


def tabla_por_nombre(plc, nombre: str):
    for tabla, _ in recorrer_tablas(plc):
        if str(tabla.Name) == nombre:
            return tabla
    nombres = [str(t.Name) for t, _ in recorrer_tablas(plc)]
    raise NoEncontrado("la tabla de variables", nombre, difflib.get_close_matches(nombre, nombres))


def todos(sesion: SesionTia, plc) -> list[TagLeido]:
    cultura = cultura_edicion(sesion.proyecto)
    return [_leer(tag, str(tabla.Name), cultura) for tabla, _ in recorrer_tablas(plc) for tag in tabla.Tags]


def de_tabla(sesion: SesionTia, plc, nombre_tabla: str) -> list[TagLeido]:
    cultura = cultura_edicion(sesion.proyecto)
    tabla = tabla_por_nombre(plc, nombre_tabla)
    return [_leer(tag, nombre_tabla, cultura) for tag in tabla.Tags]


def crear_o_actualizar(sesion: SesionTia, plc, nombre_tabla: str, definiciones: list[dict]) -> list[str]:
    """definiciones: [{"nombre", "tipo", "direccion", "comentario"}]. Idempotente.

    Los nombres de tag son únicos en todo el PLC: si ya existe en otra tabla, se actualiza ahí.
    """
    _validar_definiciones(definiciones)
    tabla = plc.TagTableGroup.TagTables.Find(nombre_tabla) or plc.TagTableGroup.TagTables.Create(nombre_tabla)
    existentes = {str(t.Name): (t, str(tb.Name)) for tb, _ in recorrer_tablas(plc) for t in tb.Tags}
    idioma = sesion.proyecto.LanguageSettings.EditingLanguage
    informe = []
    for d in definiciones:
        nombre, tipo, direccion = d["nombre"], d.get("tipo", "Bool"), d["direccion"]
        if nombre in existentes:
            tag, tabla_actual = existentes[nombre]
            tag.DataTypeName, tag.LogicalAddress = tipo, direccion
            informe.append(f"= {nombre} {tipo} {direccion} (actualizado en '{tabla_actual}')")
        else:
            tag = tabla.Tags.Create(nombre, tipo, direccion)
            informe.append(f"+ {nombre} {tipo} {direccion}")
        if d.get("comentario"):
            _poner_comentario(tag, idioma, d["comentario"])
    return informe


def borrar(plc, nombre: str) -> str:
    for tabla, _ in recorrer_tablas(plc):
        tag = tabla.Tags.Find(nombre)
        if tag is not None:
            tag.Delete()
            return f"Tag {nombre} borrado de '{tabla.Name}'."
    raise NoEncontrado("el tag", nombre)


_FLAGS_ACCESO = ("ExternalAccessible", "ExternalVisible", "ExternalWritable")


def organizar(sesion: SesionTia, plc, reglas: list[dict] | None = None, aplicar: bool = False,
              solo_tabla: str | None = None) -> list[str]:
    """Clasifica los tags en tablas por categoría. Por defecto SOLO SIMULA y muestra el plan."""
    reglas_efectivas = ([ReglaCategoria.desde_dict(r) for r in reglas] if reglas else list(REGLAS_SUGERIDAS))
    movimientos, sin_categoria = planificar(todos(sesion, plc), reglas_efectivas, solo_tabla)
    plan = resumen_plan(movimientos, sin_categoria)
    if not aplicar:
        return ["SIMULACIÓN: no se movió nada. Revisa el plan y repite con aplicar=true.", *plan]
    hechos = [_mover(plc, m.tag, m.destino) for m in movimientos]
    # Recrear tags deja inconsistentes los bloques que los usan: se recompila para reenlazarlos.
    compilacion = compilar(sesion, plc).resumen() if hechos else ""
    return [f"Aplicado: {len(hechos)} tags movidos.", *hechos,
            *([f"Sin categoría: {', '.join(sin_categoria)}"] if sin_categoria else []), compilacion]


def _mover(plc, nombre: str, nombre_destino: str) -> str:
    """Openness V17 no puede mover tags: se copia todo (comentarios en todos los idiomas y flags),
    se borra y se recrea en la tabla destino. Los bloques lo referencian por nombre."""
    tag, tabla_origen = _buscar_con_tabla(plc, nombre)
    destino = plc.TagTableGroup.TagTables.Find(nombre_destino) or plc.TagTableGroup.TagTables.Create(nombre_destino)
    datos = (str(tag.DataTypeName), str(tag.LogicalAddress))
    comentarios = [(item.Language, str(item.Text or "")) for item in tag.Comment.Items]
    flags = {f: _leer_atributo(tag, f) for f in _FLAGS_ACCESO}
    tag.Delete()
    try:
        nuevo = destino.Tags.Create(nombre, *datos)
    except Exception:
        tabla_origen.Tags.Create(nombre, *datos)  # devolverlo a su sitio antes de informar el fallo
        raise
    for idioma, texto in comentarios:
        item = nuevo.Comment.Items.Find(idioma)
        if item is not None and texto:
            item.Text = texto
    for flag, valor in flags.items():
        if valor is not None:
            nuevo.SetAttribute(flag, valor)
    return f"  {nombre}: '{tabla_origen.Name}' -> '{nombre_destino}'"


def _buscar_con_tabla(plc, nombre: str):
    for tabla, _ in recorrer_tablas(plc):
        tag = tabla.Tags.Find(nombre)
        if tag is not None:
            return tag, tabla
    raise NoEncontrado("el tag", nombre)


def _leer_atributo(objeto, nombre: str):
    try:
        return objeto.GetAttribute(nombre)
    except Exception:
        return None


def _leer(tag, tabla: str, cultura: str) -> TagLeido:
    return TagLeido(nombre=str(tag.Name), tipo=str(tag.DataTypeName), direccion=str(tag.LogicalAddress or ""),
                    comentario=texto_multilingue(tag.Comment, cultura), tabla=tabla)


def texto_multilingue(texto, cultura: str) -> str:
    """Texto en el idioma de edición; si está vacío, el primero que tenga contenido."""
    try:
        items = list(texto.Items)
    except Exception:
        return ""
    preferido = [i for i in items if str(i.Language.Culture.Name) == cultura]
    for item in preferido + items:
        if str(item.Text or "").strip():
            return str(item.Text).strip()
    return ""


def _poner_comentario(tag, idioma, comentario: str) -> None:
    item = tag.Comment.Items.Find(idioma)
    if item is not None:
        item.Text = comentario


def _validar_definiciones(definiciones: list[dict]) -> None:
    for d in definiciones:
        if not d.get("nombre") or not d.get("direccion"):
            raise EntradaInvalida(f"Cada tag necesita 'nombre' y 'direccion' (ej. %I0.0): {d}")
        if not str(d["direccion"]).startswith("%"):
            raise EntradaInvalida(f"Dirección no válida '{d['direccion']}': debe empezar con % (ej. %Q0.0).")
