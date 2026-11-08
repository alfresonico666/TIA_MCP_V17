"""Prueba de punta a punta contra TIA Portal V17 real (sin PLC: todo offline).

Crea un proyecto de prueba en .pruebas/, programa KOP + SCL + UDT + PID, compila, analiza y
configura la red. Úsalo para validar una instalación nueva:

    .venv\\Scripts\\python scripts\\prueba_en_vivo.py            (TIA oculto, más rápido)
    .venv\\Scripts\\python scripts\\prueba_en_vivo.py --interfaz (ver TIA mientras trabaja)

La primera vez TIA pide autorizar a Python (Openness): responde "Sí a todo".
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PRUEBAS = RAIZ / ".pruebas"
os.environ.setdefault("TIA_MCP_RUTAS_PERMITIDAS", f"{PRUEBAS};{Path.home() / 'Proyectos' / '_copias'}")
os.environ.setdefault("TIA_MCP_DIR_CONOCIMIENTO", str(PRUEBAS / "conocimiento"))

from tia_mcp.analisis import arbol_llamadas, diagnostico  # noqa: E402
from tia_mcp.analisis.referencias import referencias  # noqa: E402
from tia_mcp.openness import (  # noqa: E402
    bloques,
    conocimiento,
    hardware,
    proyecto,
    red,
    tags,
    tecnologia,
)
from tia_mcp.openness.compilacion import compilar  # noqa: E402
from tia_mcp.servidor import crear_servidor  # noqa: E402
from tia_mcp.simaticml.lector import leer_bloque  # noqa: E402
from tia_mcp.simaticml.texto import bloque_como_texto  # noqa: E402

CPU = "6ES7 214-1BG40-0XB0/V4.5"  # S7-1214C AC/DC/RLY

UDT_MOTOR = '''TYPE "UDT_Motor"
VERSION : 0.1
   STRUCT
      Marcha : Bool;   // Orden de marcha
      EnFalla : Bool;  // Térmico disparado
      Horas : Real;    // Horas de funcionamiento
   END_STRUCT;
END_TYPE
'''

FB_ARRANQUE = {
    "tipo": "FB", "nombre": "FB_ArranqueParo", "titulo": "Arranque y paro de motor",
    "interfaz": {
        "Input": [{"nombre": "Marcha"}, {"nombre": "Paro_NC"}, {"nombre": "Termico_NC"}],
        "Output": [{"nombre": "Motor"}, {"nombre": "Arrancado"}],
        "Static": [{"nombre": "T_Arranque", "tipo": "TON_TIME"}, {"nombre": "Estado", "tipo": '"UDT_Motor"'}],
    },
    "redes": [
        {"titulo": "Arranque y paro con retención",
         "logica": [{"paralelo": [{"contacto": "#Marcha"}, {"contacto": "#Motor"}]},
                    {"contacto": "#Paro_NC"}, {"contacto": "#Termico_NC"}, {"bobina": "#Motor"}]},
        {"titulo": "Confirmación de arranque (5 s)",
         "logica": [{"contacto": "#Motor"},
                    {"caja": "TON", "instancia": "#T_Arranque", "entradas": {"PT": "T#5s"}},
                    {"bobina": "#Arrancado"}]},
        {"titulo": "Falla térmica al UDT",
         "logica": [{"contacto": "#Termico_NC", "negado": True}, {"bobina": "#Estado.EnFalla"}]},
    ],
}

MAIN = {"tipo": "OB", "nombre": "Main", "numero": 1, "titulo": "Programa principal", "redes": [
    {"titulo": "Motor 1", "logica": {"llamar": "FB_ArranqueParo", "instancia": "DB_ArranqueParo",
                                     "parametros": {"Marcha": "Marcha", "Paro_NC": "Paro_NC",
                                                    "Termico_NC": "Termico_NC", "Motor": "Motor"}}},
    {"titulo": "Piloto", "logica": [{"contacto": "Motor"}, {"bobina": "Piloto"}]},
]}

FB_TANQUE = '''FUNCTION_BLOCK "FB_Tanque"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
   VAR_INPUT
      Nivel : Real;
   END_VAR
   VAR_OUTPUT
      Bomba : Bool;
   END_VAR
BEGIN
   IF #Nivel < 20.0 THEN
      #Bomba := TRUE;
   ELSIF #Nivel > 80.0 THEN
      #Bomba := FALSE;
   END_IF;
END_FUNCTION_BLOCK
'''

OB_PID = '''ORGANIZATION_BLOCK "Cyclic interrupt"
{ S7_Optimized_Access := 'TRUE' }
VERSION : 0.1
BEGIN
   "PID_Compact_1"(Setpoint := 50.0, Input := "Temperatura", Output => "Salida_PID");
END_ORGANIZATION_BLOCK
'''


class Prueba:
    def __init__(self) -> None:
        self.fallos: list[str] = []

    def paso(self, titulo: str, funcion, *args, **kwargs):
        inicio = time.time()
        print(f"\n=== {titulo}", flush=True)
        try:
            resultado = funcion(*args, **kwargs)
            texto = resultado if isinstance(resultado, str) else "\n".join(map(str, resultado or []))
            print(texto[:3000])
            print(f"--- OK ({time.time() - inicio:.1f} s)", flush=True)
            return resultado
        except Exception as e:  # la prueba sigue para ver todos los fallos
            self.fallos.append(f"{titulo}: {type(e).__name__}: {e}")
            print(f"--- FALLO: {type(e).__name__}: {e}", flush=True)
            return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interfaz", action="store_true")
    args = parser.parse_args()
    nombre = "PruebaMCP"
    if (PRUEBAS / nombre).exists():
        shutil.rmtree(PRUEBAS / nombre)
    _, ctx = crear_servidor()
    s, ej, p = ctx.sesion, ctx.ejecutor.ejecutar_sincrono, Prueba()

    def plc():
        return hardware.plc(s)

    ej(p.paso, "Conectar a TIA", s.conectar, args.interfaz)
    ej(p.paso, "Crear proyecto", proyecto.crear, s, str(PRUEBAS), nombre)
    ej(p.paso, "Agregar CPU 1214C AC/DC/RLY", hardware.agregar_plc, s, "PLC_1", CPU)
    ej(p.paso, "Crear tags", lambda: tags.crear_o_actualizar(s, plc(), "Tabla de variables estándar", [
        {"nombre": "Marcha", "direccion": "%I0.0", "comentario": "Pulsador marcha"},
        {"nombre": "Paro_NC", "direccion": "%I0.1", "comentario": "Pulsador paro NC"},
        {"nombre": "Termico_NC", "direccion": "%I0.2", "comentario": "Relé térmico 95-96"},
        {"nombre": "S1_Arriba", "direccion": "%I0.3", "comentario": "Final de carrera cilindro arriba"},
        {"nombre": "Motor", "direccion": "%Q0.0", "comentario": "Contactor KM1"},
        {"nombre": "Piloto", "direccion": "%Q0.1", "comentario": "Piloto marcha"},
        {"nombre": "LVDT_Prensa", "tipo": "Int", "direccion": "%IW64", "comentario": "Posición prensa"},
        {"nombre": "Temperatura", "tipo": "Real", "direccion": "%MD100"},
        {"nombre": "Salida_PID", "tipo": "Real", "direccion": "%MD104"},
    ]))
    ej(p.paso, "UDT por SCL", lambda: ctx.programador.importar_scl(plc(), UDT_MOTOR))
    ej(p.paso, "FB KOP con TON y UDT", lambda: ctx.programador.crear_kop(plc(), FB_ARRANQUE))
    ej(p.paso, "DB de instancia", lambda: bloques.crear_db_instancia(plc(), "DB_ArranqueParo", "FB_ArranqueParo"))
    ej(p.paso, "OB1 Main KOP (sobrescribe, con respaldo)", lambda: ctx.programador.crear_kop(plc(), MAIN))
    ej(p.paso, "FB SCL", lambda: ctx.programador.importar_scl(plc(), FB_TANQUE))
    for version in ("2.3", "2.2", "2.1"):
        if ej(p.paso, f"PID_Compact V{version}", lambda v=version: tecnologia.crear(
                s, plc(), "PID_Compact_1", "PID_Compact", v)) is not None:
            p.fallos = [f for f in p.fallos if not f.startswith("PID_Compact V")]
            break
    ej(p.paso, "OB30 SCL con PID", lambda: ctx.programador.importar_scl(plc(), OB_PID))
    ej(p.paso, "Compilar todo", lambda: compilar(s, plc()).resumen())
    ej(p.paso, "Leer FB KOP como texto", lambda: bloque_como_texto(
        leer_bloque(bloques.xml_de(s, bloques.buscar(plc(), "FB_ArranqueParo")))))
    ej(p.paso, "Referencias cruzadas de Motor", lambda: [
        f"{r.bloque} red {r.red}: {r.acceso.value} {r.instruccion}"
        for r in referencias(ctx.indice.leer(s, plc()).bloques, "Motor")])
    ej(p.paso, "Árbol de llamadas", lambda: arbol_llamadas.arbol_texto(ctx.indice.leer(s, plc()).bloques))
    ej(p.paso, "Diagnóstico", lambda: diagnostico.diagnosticar(ctx.indice.programa(s, plc())))
    ej(p.paso, "Parámetros PID (filtro Setpoint)", lambda: tecnologia.parametros(plc(), "PID_Compact_1", "Setpoint"))
    ej(p.paso, "Organizar tags (simulación)", lambda: tags.organizar(s, plc()))
    ej(p.paso, "Organizar tags (aplicar)", lambda: tags.organizar(s, plc(), aplicar=True))
    ej(p.paso, "Red: IP y nombre PROFINET del PLC", red.configurar_interfaz, s, "PLC_1", "192.168.0.10",
       "255.255.255.0", "plc-banco")
    ej(p.paso, "Red: subred", red.conectar_subred, s, "PLC_1")
    ej(p.paso, "Red: agregar ET 200SP", red.agregar_dispositivo, s, "ET200SP_1", "6ES7 155-6AU01-0BN0/V4.1")
    ej(p.paso, "Red: asignar ET 200SP al PLC", red.asignar_a_plc, s, "ET200SP_1", "PLC_1")
    ej(p.paso, "Red: configurar ET 200SP", red.configurar_interfaz, s, "ET200SP_1", "192.168.0.20", None, "et200sp-1")
    ej(p.paso, "Red: interfaces", red.interfaces, s)
    ej(p.paso, "Red: direcciones E/S del PLC", red.direcciones_io, s, "PLC_1")
    ej(p.paso, "Exportar programa para Git", conocimiento.exportar_programa, s, str(PRUEBAS / "export"))
    ej(p.paso, "Guardar", proyecto.guardar, s)
    zap = PRUEBAS / "zap" / "PruebaMCP_v1.zap17"
    zap.unlink(missing_ok=True)
    ej(p.paso, "Archivar .zap17", proyecto.archivar, s, str(zap.parent), "PruebaMCP_v1")
    ej(p.paso, "Cerrar", proyecto.cerrar, s)
    shutil.rmtree(PRUEBAS / "desarchivados", ignore_errors=True)
    ej(p.paso, "Aprender desde .zap17", conocimiento.aprender, s, str(zap), str(PRUEBAS / "desarchivados"))
    ej(p.paso, "Desconectar", s.desconectar)
    ctx.ejecutor.cerrar()
    print("\n" + ("TODO OK" if not p.fallos else "FALLOS:\n  " + "\n  ".join(p.fallos)))
    return 1 if p.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
