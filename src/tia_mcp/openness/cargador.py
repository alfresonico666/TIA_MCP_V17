"""Carga perezosa de Siemens.Engineering.dll (Openness V17) mediante pythonnet.

Es el único módulo que conoce cómo se arranca .NET. El resto del paquete pide
los tipos a través de `api()` y nunca importa `clr` directamente.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from functools import cache
from types import SimpleNamespace

from ..configuracion import Configuracion
from ..errores import OpennessNoDisponible

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiOpenness:
    """Tipos .NET usados por el servidor, agrupados por espacio de nombres."""
    engineering: SimpleNamespace
    sistema: SimpleNamespace


@cache
def api(config: Configuracion) -> ApiOpenness:
    if not config.dll_openness.exists():
        raise OpennessNoDisponible(
            f"No se encontró {config.dll_openness}. ¿Está instalado TIA Portal V17 con Openness? "
            f"Si está en otra carpeta, define TIA_MCP_DIR_TIA."
        )
    _iniciar_runtime_netfx()
    _registrar_resolutor_dependencias(config)
    import clr  # noqa: PLC0415 - solo existe tras iniciar pythonnet

    clr.AddReference(str(config.dll_openness))
    log.info("Openness cargado desde %s", config.dll_openness)
    return ApiOpenness(engineering=_tipos_engineering(), sistema=_tipos_sistema())


def _iniciar_runtime_netfx() -> None:
    from pythonnet import load  # noqa: PLC0415

    with contextlib.suppress(RuntimeError):  # RuntimeError = el runtime ya estaba cargado
        load("netfx")  # Openness V17 corre sobre .NET Framework 4.8


def _registrar_resolutor_dependencias(config: Configuracion) -> None:
    from System import AppDomain, ResolveEventHandler  # noqa: PLC0415
    from System.Reflection import Assembly, AssemblyName  # noqa: PLC0415

    carpeta = config.dir_dependencias_openness

    def resolver(_remitente, argumentos):
        # Siemens.Engineering.dll depende de ensamblados que están en Bin\PublicAPI.
        ruta = carpeta / f"{AssemblyName(argumentos.Name).Name}.dll"
        return Assembly.LoadFrom(str(ruta)) if ruta.exists() else None

    AppDomain.CurrentDomain.AssemblyResolve += ResolveEventHandler(resolver)


def _tipos_engineering() -> SimpleNamespace:
    import Siemens.Engineering as raiz  # noqa: PLC0415, N813 - solo existe tras cargar la DLL
    from Siemens.Engineering.Compiler import ICompilable  # noqa: PLC0415
    from Siemens.Engineering.HW.Features import NetworkInterface, SoftwareContainer  # noqa: PLC0415
    from Siemens.Engineering.SW import PlcSoftware  # noqa: PLC0415
    from Siemens.Engineering.SW.Blocks import PlcBlock, ProgrammingLanguage  # noqa: PLC0415
    from Siemens.Engineering.SW.ExternalSources import GenerateBlockOption, GenerateOptions  # noqa: PLC0415

    return SimpleNamespace(
        TiaPortal=raiz.TiaPortal, TiaPortalMode=raiz.TiaPortalMode, ProjectOpenMode=raiz.ProjectOpenMode,
        ProjectArchivationMode=raiz.ProjectArchivationMode, ExportOptions=raiz.ExportOptions,
        ImportOptions=raiz.ImportOptions, ICompilable=ICompilable, NetworkInterface=NetworkInterface,
        SoftwareContainer=SoftwareContainer, PlcSoftware=PlcSoftware, PlcBlock=PlcBlock,
        ProgrammingLanguage=ProgrammingLanguage, GenerateBlockOption=GenerateBlockOption,
        GenerateOptions=GenerateOptions,
    )


def _tipos_sistema() -> SimpleNamespace:
    from System import Version  # noqa: PLC0415
    from System.Collections.Generic import List  # noqa: PLC0415
    from System.IO import DirectoryInfo, FileInfo  # noqa: PLC0415

    return SimpleNamespace(Version=Version, List=List, DirectoryInfo=DirectoryInfo, FileInfo=FileInfo)


def implementacion(objeto):
    """pythonnet 3 devuelve el tipo declarado (interfaz); esto da el tipo concreto."""
    return getattr(objeto, "__implementation__", objeto)
