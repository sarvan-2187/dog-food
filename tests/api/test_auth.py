def test_register_then_me(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "new.user@example.com", "password": "supersecret1", "name": "New User"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "participant"

    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "new.user@example.com"


def test_register_duplicate_email_rejected(client):
    payload = {"email": "dup@example.com", "password": "supersecret1", "name": "Dup"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_register_rejects_short_password(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short", "name": "Short"},
    )
    assert r.status_code == 422


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/auth/register",
        json={"email": "login@example.com", "password": "supersecret1", "name": "Login"},
    )
    r = client.post("/api/auth/login", json={"email": "login@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_me_requires_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_clears_session(client):
    client.post(
        "/api/auth/register",
        json={"email": "logout@example.com", "password": "supersecret1", "name": "Logout"},
    )
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
