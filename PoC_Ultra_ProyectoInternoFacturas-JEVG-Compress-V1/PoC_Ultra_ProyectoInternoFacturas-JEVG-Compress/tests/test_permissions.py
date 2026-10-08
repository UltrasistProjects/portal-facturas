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


def test_provider_e_internal_no_acceden_a_archivos_minimos(client):
    for email in ("proveedor1@poc.local", "pmo@poc.local"):
        login(client, email)
        assert client.get("/admin/required-documents").status_code == 403


def test_pmo_y_proveedor_no_acceden_a_requisitos_de_alta(client):
    for email in ("proveedor1@poc.local", "pmo@poc.local"):
        login(client, email)
        assert client.get("/admin/supplier-requirements").status_code == 403


def test_pmo_y_proveedor_no_acceden_a_requisitos_del_contrato(client):
    for email in ("proveedor1@poc.local", "pmo@poc.local"):
        login(client, email)
        assert client.get("/admin/contract-requirements").status_code == 403
