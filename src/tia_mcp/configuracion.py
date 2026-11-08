"""Configuración del servidor, leída de variables de entorno con valores por defecto.

Variables (todas opcionales):
    TIA_MCP_DIR_TIA            Carpeta de instalación de TIA Portal V17.
    TIA_MCP_RUTAS_PERMITIDAS   Carpetas donde se permite abrir/crear proyectos, separadas por ';'.
                               Acepta comodines: C:\\Users\\yo\\Proyectos\\*\\tia_proyecto
    TIA_MCP_DIR_CONOCIMIENTO   Dónde se guarda lo extraído de proyectos anteriores.
    TIA_MCP_DIR_TRABAJO        Carpeta temporal para exportaciones intermedias.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

_DIR_TIA_POR_DEFECTO = Path(r"C:\Program Files\Siemens\Automation\Portal V17")
_PROYECTOS = Path.home() / "Proyectos"
_RUTAS_PERMITIDAS_POR_DEFECTO = (
    str(_PROYECTOS / "_copias"),
    str(_PROYECTOS / "*" / "tia_proyecto"),
)


@dataclass(frozen=True)
class Configuracion:
    dir_tia: Path
    rutas_permitidas: tuple[str, ...]
    dir_conocimiento: Path
    dir_trabajo: Path

    @property
    def dll_openness(self) -> Path:
        return self.dir_tia / "PublicAPI" / "V17" / "Siemens.Engineering.dll"

    @property
    def dir_dependencias_openness(self) -> Path:
        return self.dir_tia / "Bin" / "PublicAPI"

    @property
    def dir_esquemas(self) -> Path:
        return self.dir_tia / "PublicAPI" / "V17" / "Schemas"

    @classmethod
    def desde_entorno(cls) -> Configuracion:
        rutas = os.environ.get("TIA_MCP_RUTAS_PERMITIDAS")
        return cls(
            dir_tia=Path(os.environ.get("TIA_MCP_DIR_TIA", _DIR_TIA_POR_DEFECTO)),
            rutas_permitidas=_separar_rutas(rutas) if rutas else _RUTAS_PERMITIDAS_POR_DEFECTO,
            dir_conocimiento=Path(os.environ.get("TIA_MCP_DIR_CONOCIMIENTO",
                                                 _PROYECTOS / "_conocimiento_tia")),
            dir_trabajo=Path(os.environ.get("TIA_MCP_DIR_TRABAJO",
                                            Path(tempfile.gettempdir()) / "tia_mcp")),
        )


def _separar_rutas(texto: str) -> tuple[str, ...]:
    return tuple(r.strip() for r in texto.split(";") if r.strip())
