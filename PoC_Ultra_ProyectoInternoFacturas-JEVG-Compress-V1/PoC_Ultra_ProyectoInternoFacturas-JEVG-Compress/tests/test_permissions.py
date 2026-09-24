from tests.conftest import invoice_by_number, login


def test_provider_no_accede_admin(client):
    login(client, "proveedor1@poc.local")
    assert client.get("/admin/audit").status_code == 403


def test_provider_solo_ve_sus_facturas(client):
    ajena = invoice_by_number("A-CORRECTA")  # pertenece a proveedor1
    login(client, "proveedor2@poc.local")
    page = client.get("/invoices")
    assert page.status_code == 200
    assert ajena.internal_folio not in page.text
    assert client.get(f"/invoices/{ajena.id}").status_code == 404
