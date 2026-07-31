from fastapi.testclient import TestClient

from app.main import app


def login_owner(client: TestClient):
    response = client.post("/api/auth/login", json={"pin": "629911"})
    assert response.status_code == 200


def create_employee(client: TestClient, name: str, pin: str):
    login_owner(client)
    response = client.post("/api/employees", json={"name": name, "pin": pin})
    assert response.status_code in {201, 409}
    client.post("/api/auth/logout")


def login_employee(client: TestClient, code: str):
    response = client.post("/api/auth/login", json={"pin": code})
    assert response.status_code == 200


def test_seeded_dashboard_and_document_queues():
    with TestClient(app) as client:
        health = client.get("/api/health")
        login_owner(client)
        dashboard = client.get("/api/dashboard")
        documents = client.get("/api/documents")
        transports = client.get("/api/transports")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert dashboard.status_code == 200
    assert dashboard.json()["documents_total"] >= 5
    assert documents.status_code == 200
    assert transports.status_code == 200
    assert len(transports.json()) >= 6


def test_employee_cannot_access_owner_management_apis():
    with TestClient(app) as client:
        create_employee(client, "Petr Novák", "1111")
        login_employee(client, "1111")
        assert client.get("/api/dashboard").status_code == 403
        assert client.get("/api/documents").status_code == 403
        assert client.get("/api/transports").status_code == 403
        assert client.get("/api/accounting/export.csv").status_code == 403


def test_employee_statement_contains_only_own_documents():
    with TestClient(app) as client:
        create_employee(client, "Petr Novák", "1111")
        create_employee(client, "Milan Dvořák", "2222")
        login_employee(client, "1111")
        petr_documents = client.get("/api/me/documents")

        client.post("/api/auth/logout")
        login_employee(client, "2222")
        milan_documents = client.get("/api/me/documents")

    assert petr_documents.status_code == 200
    assert milan_documents.status_code == 200
    assert {item["original_name"] for item in petr_documents.json()} == {
        "CMR_2026_001.jpg", "PHM_Benzina_28-07.jpg"
    }
    assert {item["original_name"] for item in milan_documents.json()} == {
        "CMR_2026_002.pdf", "Uctenka_Shell.jpg"
    }
    assert all("gross_amount" not in item and "dispatcher" not in item for item in petr_documents.json())


def test_missing_identity_is_rejected():
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/me/documents").status_code == 401


def test_employee_login_rejects_wrong_pin():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"pin": "9999"})
    assert response.status_code == 401


def test_owner_can_create_employee():
    with TestClient(app) as client:
        login_owner(client)
        response = client.post("/api/employees", json={"name": "Jarda Nový", "pin": "4444"})

    assert response.status_code in {201, 409}
    if response.status_code == 201:
        assert response.json()["name"] == "Jarda Nový"


def test_non_numeric_pin_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"pin": "12ab"})

    assert response.status_code == 422


def test_logout_revokes_cookie_session():
    with TestClient(app) as client:
        login_owner(client)
        assert client.get("/api/dashboard").status_code == 200
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/dashboard").status_code == 401
