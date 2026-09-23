from tests.conftest import csrf, login


def test_login_correcto(client):
    response = login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert client.get("/").status_code == 200


def test_login_incorrecto_y_csrf(client):
    response = client.post("/login", data={"email": "admin@poc.local", "password": "bad", "csrf_token": csrf(client)})
    assert response.status_code == 400
    assert "Credenciales invalidas" in response.text
    assert client.post("/login", data={"email": "x@x.com", "password": "x"}).status_code == 403

