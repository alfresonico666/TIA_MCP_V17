"""Punto de entrada.

    python -m tia_mcp              servidor MCP por stdio (lo arranca Claude Code)
    python -m tia_mcp --verificar  revisa la instalación sin conectarse a TIA
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from .configuracion import Configuracion


def main() -> int:
    parser = argparse.ArgumentParser(prog="tia-mcp", description="Servidor MCP para TIA Portal V17")
    parser.add_argument("--verificar", action="store_true", help="Diagnosticar la instalación y salir")
    parser.add_argument("--debug", action="store_true", help="Logging detallado (a stderr)")
    args = parser.parse_args()
    # stdout es el canal MCP: TODO el logging va a stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.verificar:
        return verificar_instalacion()
    from .servidor import crear_servidor  # noqa: PLC0415 - import pesado solo para el servidor

    servidor, ctx = crear_servidor()
    try:
        servidor.run("stdio")
    finally:
        ctx.ejecutor.cerrar()
    return 0


def verificar_instalacion() -> int:
    config = Configuracion.desde_entorno()
    comprobaciones = [
        ("Python 3.10-3.13", (3, 10) <= sys.version_info[:2] <= (3, 13), sys.version.split()[0]),
        ("TIA Portal V17 / Openness", config.dll_openness.exists(), str(config.dll_openness)),
        ("Esquemas XSD V17", config.dir_esquemas.exists(), str(config.dir_esquemas)),
        ("Usuario en grupo 'Siemens TIA Openness'", _en_grupo_openness(), "cerrar sesión de Windows tras agregarlo"),
    ]
    ok = True
    for nombre, correcto, detalle in comprobaciones:
        ok &= correcto
        print(f"[{'OK' if correcto else 'FALTA'}] {nombre}  ({detalle})")
    if config.dll_openness.exists():
        try:
            from .openness.cargador import api  # noqa: PLC0415

            procesos = list(api(config).engineering.TiaPortal.GetProcesses())
            print(f"[OK] Openness cargado; procesos TIA abiertos: {len(procesos)}")
        except Exception as e:
            ok = False
            print(f"[FALTA] No se pudo cargar Openness: {e}")
    print(f"Rutas permitidas: {'; '.join(config.rutas_permitidas)}")
    print("Todo listo." if ok else "Corrige lo marcado como FALTA (ver README).")
    return 0 if ok else 1


def _en_grupo_openness() -> bool:
    try:
        salida = subprocess.run(["whoami", "/groups"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return False
    return "Siemens TIA Openness" in salida


if __name__ == "__main__":
    sys.exit(main())
