from tests.conftest import login


def test_provider_no_accede_admin(client):
    login(client, "proveedor1@poc.local", "Proveedor123!")
    assert client.get("/admin/audit").status_code == 403


def test_provider_solo_ve_sus_facturas(client):
    login(client, "proveedor2@poc.local", "Proveedor123!")
    page = client.get("/invoices")
    assert page.status_code == 200
    assert "FAC-2026-00002" not in page.text
    assert client.get("/invoices/2").status_code == 404

