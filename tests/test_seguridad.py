from pathlib import Path

import pytest

from tia_mcp.errores import ProyectoAjenoAbierto, RutaNoPermitida
from tia_mcp.seguridad import GuardiaRutas


@pytest.fixture
def guardia(tmp_path: Path) -> GuardiaRutas:
    return GuardiaRutas((str(tmp_path / "_copias"), str(tmp_path / "*" / "tia_proyecto")))


def test_permite_copias_y_tia_proyecto_aunque_no_existan(guardia, tmp_path):
    assert guardia.es_permitida(tmp_path / "_copias" / "Cliente" / "Linea.ap17")
    assert guardia.es_permitida(tmp_path / "MiRepo" / "tia_proyecto" / "Nuevo")
    assert guardia.es_permitida(str(tmp_path / "_COPIAS" / "x.ap17").upper())  # Windows ignora mayúsculas


def test_rechaza_originales(guardia, tmp_path):
    with pytest.raises(RutaNoPermitida):
        guardia.exigir_permitida(tmp_path / "Clientes" / "Original.ap17")
    with pytest.raises(ProyectoAjenoAbierto):
        guardia.exigir_proyecto_propio(tmp_path / "_copias_falsas" / "x.ap17")


def test_no_escapa_con_rutas_relativas(guardia, tmp_path):
    assert not guardia.es_permitida(tmp_path / "_copias" / ".." / "Original.ap17")
