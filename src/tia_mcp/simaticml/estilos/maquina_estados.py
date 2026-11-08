"""Máquinas de estados (Moore / Mealy) → bloque KOP (especificación de crear_kop) o SCL (CASE).

Estilos de programación industrial:
  - **Moore**: las salidas dependen SOLO del estado. Robusto y fácil de diagnosticar ("estoy en el paso 20,
    la válvula debe estar abierta"). Una salida cambia un ciclo después de la transición.
  - **Mealy**: las salidas dependen del estado Y de las entradas. Reacciona en el mismo ciclo (p. ej. el motor
    cae en cuanto se pulsa paro, antes de cambiar de estado) con menos estados.
  - **Banderas** (S/R con marcas) no es una máquina de estados: se programa directo con crear_kop.

Especificación:
    {"nombre": "FB_Motor_Moore", "estilo": "moore" | "mealy", "lenguaje": "kop" | "scl", "numero": 2,
     "titulo": "...", "comentario": "...",
     "entradas": [{"nombre": "Marcha", "comentario": "..."}, ...],          (Bool)
     "salidas":  [{"nombre": "Motor", "comentario": "..."}, ...],           (Bool; además se crea Estado: Int)
     "estados": [{"nombre": "REPOSO", "valor": 0, "salidas": {"Piloto_Paro": true}},
                 {"nombre": "MARCHA", "valor": 10, "salidas": {"Motor": true}},          # Moore
                 {"nombre": "MARCHA", "valor": 10, "salidas": {"Motor": ["Paro_OK", "Termico_OK"]}}],  # Mealy
     "inicial": "REPOSO",
     "transiciones": [{"desde": "REPOSO", "hacia": "MARCHA", "si": ["Marcha", "Paro_OK", "Termico_OK"]},
                      {"desde": "*", "hacia": "FALLA", "si": ["NOT Termico_OK"]}, ...]}

Condición `si`: lista de entradas en AND; anteponer "NOT " para negar. Varias transiciones entre los mismos
estados = OR. "*" como origen = desde cualquier estado (salvo el destino). Prioridad: si varias transiciones
de un mismo estado se cumplen a la vez, gana la que aparece PRIMERO en la lista.
Para evitar saltos en cascada en un mismo ciclo, las transiciones se evalúan sobre una copia del estado
tomada al inicio del bloque (#Estado_Previo).
"""
from __future__ import annotations

from dataclasses import dataclass

ESTADO = "Estado_Actual"
PREVIO = "Estado_Previo"
SALIDA_ESTADO = "Estado"


class MaquinaInvalida(ValueError):
    """Especificación de máquina de estados no válida (mensaje en español)."""


@dataclass(frozen=True)
class Transicion:
    desde: str
    hacia: str
    condicion: tuple[str, ...]


@dataclass
class Maquina:
    nombre: str
    estilo: str
    lenguaje: str
    numero: int | None
    titulo: str
    comentario: str
    entradas: list[dict]
    salidas: list[dict]
    estados: dict[str, int]                       # nombre -> valor
    salidas_por_estado: dict[str, dict[str, object]]
    inicial: str
    transiciones: list[Transicion]


# --------------------------------------------------------------------------- lectura y validación
def leer_maquina(spec: dict) -> Maquina:
    estilo = str(spec.get("estilo", "moore")).lower()
    lenguaje = str(spec.get("lenguaje", "kop")).lower()
    if estilo not in ("moore", "mealy"):
        raise MaquinaInvalida(f"estilo '{estilo}' no válido: usa 'moore' o 'mealy'.")
    if lenguaje not in ("kop", "scl"):
        raise MaquinaInvalida(f"lenguaje '{lenguaje}' no válido: usa 'kop' o 'scl'.")
    nombre = _requerido(spec, "nombre")
    entradas = [_variable(e, "entrada") for e in spec.get("entradas", [])]
    salidas = [_variable(s, "salida") for s in spec.get("salidas", [])]
    nombres_entradas = {e["nombre"] for e in entradas}
    nombres_salidas = {s["nombre"] for s in salidas}
    reservados = {ESTADO, PREVIO, SALIDA_ESTADO}
    if (nombres_entradas | nombres_salidas) & reservados:
        raise MaquinaInvalida(f"Nombres reservados por la máquina: {', '.join(sorted(reservados))}.")
    estados, salidas_por_estado = _leer_estados(_requerido(spec, "estados"), estilo, nombres_entradas,
                                                nombres_salidas)
    inicial = spec.get("inicial") or next(iter(estados))
    if inicial not in estados:
        raise MaquinaInvalida(f"Estado inicial '{inicial}' no existe.")
    transiciones = _leer_transiciones(_requerido(spec, "transiciones"), estados, nombres_entradas)
    for s in nombres_salidas:
        if not any(s in sal for sal in salidas_por_estado.values()):
            raise MaquinaInvalida(f"La salida '{s}' no se activa en ningún estado.")
    return Maquina(nombre, estilo, lenguaje, spec.get("numero"), spec.get("titulo", ""), spec.get("comentario", ""),
                   entradas, salidas, estados, salidas_por_estado, inicial, transiciones)


def _leer_estados(lista: list[dict], estilo: str, entradas: set[str],
                  salidas: set[str]) -> tuple[dict[str, int], dict[str, dict[str, object]]]:
    estados: dict[str, int] = {}
    salidas_por_estado: dict[str, dict[str, object]] = {}
    for e in lista:
        nombre_estado = _requerido(e, "nombre")
        valor = int(_requerido(e, "valor"))
        if nombre_estado in estados or valor in estados.values():
            raise MaquinaInvalida(f"Estado repetido (nombre o valor): {nombre_estado}={valor}.")
        estados[nombre_estado] = valor
        sal = dict(e.get("salidas", {}))
        for s, valor_salida in sal.items():
            if s not in salidas:
                raise MaquinaInvalida(f"El estado {nombre_estado} usa la salida '{s}', que no está en `salidas`.")
            if isinstance(valor_salida, list):
                if estilo == "moore":
                    raise MaquinaInvalida(f"Estado {nombre_estado}: en Moore las salidas dependen SOLO del estado "
                                          f"(usa true/false); condiciones con entradas = estilo 'mealy'.")
                _validar_condicion(valor_salida, entradas, f"salida {s} en {nombre_estado}")
        salidas_por_estado[nombre_estado] = sal
    return estados, salidas_por_estado


def _leer_transiciones(lista: list[dict], estados: dict[str, int], entradas: set[str]) -> list[Transicion]:
    transiciones = []
    for t in lista:
        desde, hacia = _requerido(t, "desde"), _requerido(t, "hacia")
        for e in (desde, hacia):
            if e != "*" and e not in estados:
                raise MaquinaInvalida(f"Transición con estado desconocido '{e}'.")
        if hacia == "*":
            raise MaquinaInvalida("El destino de una transición no puede ser '*'.")
        condicion = tuple(t.get("si", []))
        _validar_condicion(condicion, entradas, f"transición {desde}→{hacia}")
        origenes = [e for e in estados if e != hacia] if desde == "*" else [desde]
        transiciones += [Transicion(o, hacia, condicion) for o in origenes]
    return transiciones


def _validar_condicion(condicion, entradas: set[str], donde: str) -> None:
    for termino in condicion:
        nombre = _sin_not(termino)[0]
        if nombre not in entradas:
            raise MaquinaInvalida(f"{donde}: '{nombre}' no es una entrada declarada.")


def _sin_not(termino: str) -> tuple[str, bool]:
    t = termino.strip()
    if t.upper().startswith("NOT "):
        return t[4:].strip(), True
    return t, False


def _variable(datos: dict, que: str) -> dict:
    if "nombre" not in datos:
        raise MaquinaInvalida(f"Cada {que} necesita `nombre`.")
    return {"nombre": datos["nombre"], "tipo": "Bool", "comentario": datos.get("comentario", "")}


def _requerido(d: dict, clave: str):
    if clave not in d or d[clave] in (None, "", []):
        raise MaquinaInvalida(f"Falta `{clave}` en la especificación de la máquina de estados.")
    return d[clave]


def _transiciones_por_prioridad(m: Maquina) -> list[Transicion]:
    """En KOP gana la última escritura: se emiten en orden inverso para que gane la primera de la lista."""
    return list(reversed(m.transiciones))


# --------------------------------------------------------------------------- KOP (especificación crear_kop)
def a_kop(m: Maquina) -> dict:
    redes = []
    if m.estilo == "mealy":
        redes += _redes_salidas(m, referencia=ESTADO)
    redes.append({"titulo": "Foto del estado al inicio del ciclo",
                  "comentario": "Las transiciones se evalúan sobre esta copia: un solo salto por ciclo.",
                  "logica": [{"caja": "MOVE", "entradas": {"in": f"#{ESTADO}"}, "salidas": {"out1": f"#{PREVIO}"}}]})
    nombre_de = {v: k for k, v in m.estados.items()}
    for t in _transiciones_por_prioridad(m):
        logica = [{"comparar": [f"#{PREVIO}", "==", str(m.estados[t.desde])], "tipo": "Int"}]
        logica += [_contacto(c) for c in t.condicion]
        logica.append({"caja": "MOVE", "entradas": {"in": str(m.estados[t.hacia])},
                       "salidas": {"out1": f"#{ESTADO}"}})
        redes.append({"titulo": f"{t.desde} -> {t.hacia}",
                      "comentario": f"Si estado = {t.desde} ({m.estados[t.desde]})"
                                    + (f" y {' Y '.join(t.condicion)}" if t.condicion else "")
                                    + f" pasa a {t.hacia} ({m.estados[t.hacia]}).",
                      "logica": logica})
    if m.estilo == "moore":
        redes += _redes_salidas(m, referencia=ESTADO)
    redes.append({"titulo": "Estado para HMI / diagnóstico",
                  "comentario": "; ".join(f"{v} = {nombre_de[v]}" for v in sorted(nombre_de)),
                  "logica": [{"caja": "MOVE", "entradas": {"in": f"#{ESTADO}"},
                              "salidas": {"out1": f"#{SALIDA_ESTADO}"}}]})
    spec = {
        "tipo": "FB", "nombre": m.nombre, "titulo": m.titulo or f"Máquina de estados {m.estilo.capitalize()}",
        "comentario": m.comentario or _comentario_estilo(m),
        "interfaz": {
            "Input": m.entradas,
            "Output": [*m.salidas, {"nombre": SALIDA_ESTADO, "tipo": "Int", "comentario": "Estado actual"}],
            "Static": [{"nombre": ESTADO, "tipo": "Int", "comentario": "Estado de la máquina",
                        "valor_inicial": str(m.estados[m.inicial])}],
            "Temp": [{"nombre": PREVIO, "tipo": "Int", "comentario": "Estado al inicio del ciclo"}],
        },
        "redes": redes,
    }
    if m.numero is not None:
        spec["numero"] = int(m.numero)
    return spec


def _redes_salidas(m: Maquina, referencia: str) -> list[dict]:
    redes = []
    for salida in m.salidas:
        s = salida["nombre"]
        ramas = []
        for estado, sal in m.salidas_por_estado.items():
            valor = sal.get(s)
            if valor is True or (isinstance(valor, list)):
                rama = [{"comparar": [f"#{referencia}", "==", str(m.estados[estado])], "tipo": "Int"}]
                if isinstance(valor, list):
                    rama += [_contacto(c) for c in valor]
                ramas.append(rama[0] if len(rama) == 1 else {"serie": rama})
        if not ramas:
            continue
        condicion = ramas[0] if len(ramas) == 1 else {"paralelo": ramas}
        activos = [e for e, sal in m.salidas_por_estado.items() if sal.get(s) not in (None, False)]
        redes.append({"titulo": f"Salida {s}",
                      "comentario": ("Moore: solo depende del estado " if m.estilo == "moore"
                                     else "Mealy: depende del estado y de las entradas ")
                                    + f"({', '.join(activos)}).",
                      "logica": [condicion, {"bobina": f"#{s}"}]})
    return redes


def _contacto(termino: str) -> dict:
    nombre, negado = _sin_not(termino)
    return {"contacto": f"#{nombre}", "negado": True} if negado else {"contacto": f"#{nombre}"}


def _comentario_estilo(m: Maquina) -> str:
    base = ("Moore: las salidas dependen solo del estado." if m.estilo == "moore"
            else "Mealy: las salidas dependen del estado y de las entradas (reaccion en el mismo ciclo).")
    return f"{base} Generado por TIA_MCP_V17 (crear_maquina_estados)."


# --------------------------------------------------------------------------- SCL
def a_scl(m: Maquina) -> str:
    """FB en SCL con CASE. Solo ASCII (TIA rechaza acentos en identificadores; en comentarios se evitan)."""
    nombre_de = {v: k for k, v in m.estados.items()}
    lineas = [f'FUNCTION_BLOCK "{m.nombre}"',
              f"TITLE = {_ascii(m.titulo or 'Maquina de estados ' + m.estilo.capitalize())}",
              "{ S7_Optimized_Access := 'TRUE' }", "VERSION : 0.1", "   VAR_INPUT"]
    lineas += [f"      {e['nombre']} : Bool;{_coment(e['comentario'])}" for e in m.entradas]
    lineas += ["   END_VAR", "   VAR_OUTPUT"]
    lineas += [f"      {s['nombre']} : Bool;{_coment(s['comentario'])}" for s in m.salidas]
    lineas += [f"      {SALIDA_ESTADO} : Int;   // Estado actual (HMI)", "   END_VAR", "   VAR",
               f"      {ESTADO} : Int := {m.estados[m.inicial]};   // Estado de la maquina", "   END_VAR",
               "   VAR_TEMP", f"      {PREVIO} : Int;   // Estado al inicio del ciclo", "   END_VAR", "", "BEGIN",
               f"   // {_ascii(_comentario_estilo(m))}",
               "   // Estados: " + ", ".join(f"{v} = {nombre_de[v]}" for v in sorted(nombre_de))]
    if m.estilo == "mealy":
        lineas += _scl_salidas(m)
    lineas += ["", "   // --- Transiciones (sobre la foto del estado: un salto por ciclo) ---",
               f"   #{PREVIO} := #{ESTADO};", f"   CASE #{PREVIO} OF"]
    for estado, valor in m.estados.items():
        salientes = [t for t in m.transiciones if t.desde == estado]
        if not salientes:
            continue
        lineas.append(f"      {valor}: // {estado}")
        for i, t in enumerate(salientes):
            palabra = "IF" if i == 0 else "ELSIF"
            lineas.append(f"         {palabra} {_scl_condicion(t.condicion)} THEN")
            lineas.append(f"            #{ESTADO} := {m.estados[t.hacia]};   // -> {t.hacia}")
        lineas.append("         END_IF;")
    lineas.append(f"      ELSE  // estado desconocido: volver al inicial\n         #{ESTADO} := "
                  f"{m.estados[m.inicial]};")
    lineas.append("   END_CASE;")
    if m.estilo == "moore":
        lineas += _scl_salidas(m)
    lineas += ["", f"   #{SALIDA_ESTADO} := #{ESTADO};", "END_FUNCTION_BLOCK", ""]
    return "\n".join(lineas)


def _scl_salidas(m: Maquina) -> list[str]:
    lineas = ["", "   // --- Salidas (" + ("solo dependen del estado" if m.estilo == "moore"
                                            else "estado actual + entradas") + ") ---"]
    for salida in m.salidas:
        s = salida["nombre"]
        terminos = []
        for estado, sal in m.salidas_por_estado.items():
            valor = sal.get(s)
            if valor is True:
                terminos.append(f"#{ESTADO} = {m.estados[estado]}")
            elif isinstance(valor, list):
                terminos.append(f"(#{ESTADO} = {m.estados[estado]} AND {_scl_condicion(valor)})")
        lineas.append(f"   #{s} := {' OR '.join(terminos) if terminos else 'FALSE'};")
    return lineas


def _scl_condicion(condicion) -> str:
    if not condicion:
        return "TRUE"
    partes = []
    for t in condicion:
        nombre, negado = _sin_not(t)
        partes.append(f"NOT #{nombre}" if negado else f"#{nombre}")
    return " AND ".join(partes)


def _coment(texto: str) -> str:
    return f"   // {_ascii(texto)}" if texto else ""


def _ascii(texto: str) -> str:
    import unicodedata  # noqa: PLC0415
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


# --------------------------------------------------------------------------- documentación
def diagrama_mermaid(m: Maquina) -> str:
    """Diagrama de estados (Mermaid stateDiagram-v2) para la documentación del proyecto."""
    lineas = ["stateDiagram-v2", f"    [*] --> {m.inicial}"]
    for t in m.transiciones:
        etiqueta = " Y ".join(t.condicion) if t.condicion else "siempre"
        lineas.append(f"    {t.desde} --> {t.hacia} : {etiqueta}")
    for estado, sal in m.salidas_por_estado.items():
        activas = [s if v is True else f"{s} si {' Y '.join(v)}" for s, v in sal.items() if v not in (None, False)]
        if activas:
            lineas.append(f"    {estado} : {estado} [{m.estados[estado]}] / {', '.join(activas)}")
    return "\n".join(lineas)
