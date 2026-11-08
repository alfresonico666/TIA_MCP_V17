"""Análisis sin TIA: referencias, árbol de llamadas, diagnóstico, direcciones, SCL y estilo."""
from dataclasses import dataclass

from tia_mcp.analisis import diagnostico as dx
from tia_mcp.analisis.arbol_llamadas import arbol_texto, no_llamados
from tia_mcp.analisis.direcciones import siguiente_libre, solapamientos
from tia_mcp.analisis.estilo import perfil
from tia_mcp.analisis.organizar_tags import REGLAS_SUGERIDAS, ReglaCategoria, planificar
from tia_mcp.analisis.referencias import referencias
from tia_mcp.scl import usos as usos_scl
from tia_mcp.scl.verificacion import verificar
from tia_mcp.simaticml.kop.desde_json import bloque_desde_json
from tia_mcp.simaticml.kop.generador import documento
from tia_mcp.simaticml.lector import leer_bloque
from tia_mcp.simaticml.modelo import Acceso


@dataclass
class TagFalso:
    nombre: str
    direccion: str
    comentario: str = ""


def _bloque(tipo, nombre, numero, redes, interfaz=None):
    datos = {"tipo": tipo, "nombre": nombre, "numero": numero, "interfaz": interfaz or {},
             "redes": [{"titulo": f"Red {i}", "logica": r} for i, r in enumerate(redes, 1)]}
    tipos = {"FB_Motor": {"Marcha": ("Input", "Bool"), "Motor": ("Output", "Bool")}}
    return leer_bloque(documento(bloque_desde_json(datos, lambda b: tipos[b])))


def _programa():
    fb = _bloque("FB", "FB_Motor", 1, [[{"contacto": "#Marcha"}, {"bobina": "#Motor"}]],
                 {"Input": [{"nombre": "Marcha"}], "Output": [{"nombre": "Motor"}]})
    huerfano = _bloque("FC", "FC_Olvidado", 2, [[{"contacto": "Lampara"}, {"bobina": "Lampara"}]])
    main = _bloque("OB", "Main", 1, [
        {"llamar": "FB_Motor", "instancia": "DB_M1", "parametros": {"Marcha": "Marcha", "Motor": "Motor"}},
        {"llamar": "FB_Motor", "instancia": "DB_M1", "parametros": {"Marcha": "Marcha2", "Motor": "Motor"}},
        [{"contacto": "Falla"}, {"set": "Alarma"}],
        [{"contacto": "Auto"}, {"bobina": "Piloto"}],
        [{"contacto": "Manual"}, {"bobina": "Piloto"}],
    ])
    tags = [TagFalso("Marcha", "%I0.0"), TagFalso("Motor", "%Q0.0"), TagFalso("Auto", "%M0.0"),
            TagFalso("Piloto", "%Q0.1"), TagFalso("Sobrante", "%M0.1"), TagFalso("Palabra", "%MW0")]
    return dx.Programa(bloques=[fb, huerfano, main], tags=tags)


def test_referencias_cruzadas_por_nombre_con_o_sin_comillas():
    p = _programa()
    refs = referencias(p.bloques, "Motor")
    assert {(r.bloque, r.acceso) for r in refs} == {("Main", Acceso.ESCRITURA)}
    assert referencias(p.bloques, '"Piloto"')[0].instruccion == "Coil"


def test_arbol_y_no_llamados():
    p = _programa()
    assert arbol_texto(p.bloques) == ["Main", '  FB_Motor  ("DB_M1")']
    assert no_llamados(p.bloques) == ["FC_Olvidado"]


def test_diagnostico_detecta_problemas_tipicos():
    reglas = {h.regla: h for h in dx.diagnosticar(_programa())}
    assert "Piloto" in reglas["doble bobina"].mensaje
    assert "Alarma" in reglas["set sin reset"].mensaje
    assert reglas["instancia compartida"].gravedad == "error"
    assert "FC_Olvidado" in reglas["bloque no llamado"].mensaje
    assert "Sobrante" in reglas["tags sin uso"].mensaje
    assert "Auto" in reglas["leída sin escribir"].mensaje  # %M0.0 se lee y nadie la escribe
    assert "Palabra" in reglas["direcciones solapadas"].mensaje


def test_direcciones():
    tags = [("A", "%M0.0"), ("B", "%MB0"), ("C", "%M1.0")]
    assert solapamientos(tags) == [("A", "%M0.0", "B", "%MB0")]
    assert siguiente_libre(tags, "M") == "%M1.1"
    assert siguiente_libre(tags, "M", "Int") == "%MW2"


def test_scl_usos_y_llamadas():
    fuente = '''FUNCTION_BLOCK "FB_Tanque"
VAR_INPUT Nivel : Real; END_VAR
BEGIN
  // comentario con "Falso"
  IF #Nivel > "Limites".Maximo THEN
     "Bomba" := FALSE;
  END_IF;
  "DB_Valvula"(Abrir := #Nivel < 10.0, Abierta => #Estado);
END_FUNCTION_BLOCK'''
    usos, llamadas = usos_scl.analizar(fuente)
    escritos = {u.operando for u in usos if u.acceso == Acceso.ESCRITURA}
    leidos = {u.operando for u in usos if u.acceso == Acceso.LECTURA}
    assert escritos == {'"Bomba"', "#Estado"}
    assert {"#Nivel", '"Limites".Maximo'} <= leidos and '"Falso"' not in leidos
    assert [ll.bloque for ll in llamadas] == ['"DB_Valvula"']


def test_verificacion_scl():
    ok = verificar('FUNCTION_BLOCK "FB_X"\nVAR_INPUT a : Bool; END_VAR\nBEGIN\nIF #a THEN ; END_IF;\n'
                   'END_FUNCTION_BLOCK\nTYPE "UDT_Motor"\nSTRUCT\n x : Bool;\nEND_STRUCT;\nEND_TYPE\n')
    assert ok.correcto and ok.bloques == ['FUNCTION_BLOCK "FB_X"', 'TYPE "UDT_Motor"']
    malo = verificar('FUNCTION_BLOCK "FB_X"\nBEGIN\nIF #a THEN\n#Señal := 1;\n')
    assert not malo.correcto and any("IF" in e for e in malo.errores) and malo.advertencias


def test_perfil_de_estilo():
    p = _programa()
    texto = perfil("Demo", p.bloques, p.tags)
    assert "# Perfil de estilo: Demo" in texto and "FB_" in texto and "## Árbol de llamadas" in texto


@dataclass
class TagCompleto:
    nombre: str
    tipo: str
    direccion: str
    comentario: str
    tabla: str = "Tabla de variables estándar"


def test_organizar_tags_simula_plan_con_reglas_sugeridas_y_propias():
    tags = [TagCompleto("LVDT_Prensa", "Int", "%IW64", "Posición prensa"),
            TagCompleto("S1_Arriba", "Bool", "%I0.0", "Final de carrera cilindro arriba"),
            TagCompleto("Marcha", "Bool", "%I0.1", "Pulsador marcha"),
            TagCompleto("Motor", "Bool", "%Q0.0", "", tabla="Motores"),
            TagCompleto("Aux", "Bool", "%M5.0", ""),
            TagCompleto("Raro", "Bool", "%DB1.DBX0.0", "")]
    movimientos, sin_categoria = planificar(tags, REGLAS_SUGERIDAS)
    destino = {m.tag: m.destino for m in movimientos}
    assert destino == {"LVDT_Prensa": "LVDTs", "S1_Arriba": "Finales_de_carrera",
                       "Marcha": "Pulsadores_y_selectores", "Aux": "Marcas"}  # Motor ya está en su tabla
    assert sin_categoria == ["Raro"]
    propias = [ReglaCategoria.desde_dict({"tabla": "Prensa", "prefijos": ["LVDT"], "direcciones": ["%IW64"],
                                          "todas": True})]
    assert [m.destino for m in planificar(tags, propias)[0]] == ["Prensa"]
