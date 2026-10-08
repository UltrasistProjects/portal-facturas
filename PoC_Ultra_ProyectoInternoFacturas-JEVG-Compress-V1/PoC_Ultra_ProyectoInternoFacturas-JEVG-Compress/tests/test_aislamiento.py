from pathlib import Path

from tests.conftest import ROOT, TEST_DATABASE, TEST_ROOT, WORK_URL


def test_bd_y_almacenamiento_de_pruebas_son_temporales():
    from app.core.config import settings
    from app.core.database import engine

    database = engine.url.database
    assert database == TEST_DATABASE
    assert database.startswith("portal_test_")
    if WORK_URL is not None:
        assert database != WORK_URL.database
    storage = Path(settings.storage_path).resolve()
    assert TEST_ROOT in storage.parents
    assert ROOT not in storage.parents
