from pathlib import Path

import pytest

from tia_mcp.configuracion import Configuracion
from tia_mcp.simaticml.validador_xsd import ValidadorXsd

MUESTRAS = Path(__file__).parent / "muestras"


@pytest.fixture(scope="session")
def validador() -> ValidadorXsd:
    v = ValidadorXsd(Configuracion.desde_entorno().dir_esquemas)
    if not v.disponible:
        pytest.skip("XSD de TIA V17 no instalados en esta PC")
    return v


@pytest.fixture
def arranque_paro_json() -> dict:
    return {
        "tipo": "FB", "nombre": "FB_ArranqueParo", "numero": 1,
        "titulo": "Arranque y paro de motor",
        "interfaz": {
            "Input": [{"nombre": "Marcha"}, {"nombre": "Paro_NC"}, {"nombre": "Termico_NC"}],
            "Output": [{"nombre": "Motor", "comentario": "Contactor KM1"}],
            "Static": [{"nombre": "T_Arranque", "tipo": "TON_TIME"}],
        },
        "redes": [{
            "titulo": "Arranque y paro con retención",
            "logica": [
                {"paralelo": [{"contacto": "#Marcha"}, {"contacto": "#Motor"}]},
                {"contacto": "#Paro_NC"},
                {"contacto": "#Termico_NC"},
                {"bobina": "#Motor"},
            ],
        }],
    }
