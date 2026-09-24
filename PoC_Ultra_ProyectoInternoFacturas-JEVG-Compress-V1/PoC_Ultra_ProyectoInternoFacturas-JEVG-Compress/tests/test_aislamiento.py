from pathlib import Path

from tests.conftest import ROOT, TEST_ROOT


def test_bd_y_almacenamiento_de_pruebas_son_temporales():
    from app.core.config import settings
    from app.core.database import engine

    database = Path(engine.url.database).resolve()
    storage = Path(settings.storage_path).resolve()
    assert TEST_ROOT in database.parents
    assert TEST_ROOT in storage.parents
    assert ROOT not in database.parents
    assert ROOT not in storage.parents
