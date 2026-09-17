import pytest


@pytest.mark.asyncio
async def test_landing_page_is_available(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Payments that" in response.text
    assert "Open API explorer" in response.text


@pytest.mark.asyncio
async def test_authentication_is_required(client, payment_payload):
    response = await client.post(
        "/payments", json=payment_payload, headers={"Idempotency-Key": "auth-test"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_create_and_get_payment(client, auth_headers, payment_payload):
    response = await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "create-1"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "SUCCESS"
    assert created["risk_level"] == "LOW"
    assert created["transaction_id"].startswith("pay_")

    fetched = await client.get(f"/payments/{created['transaction_id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["transaction_id"] == created["transaction_id"]


@pytest.mark.asyncio
async def test_idempotent_replay_returns_original_payment(client, auth_headers, payment_payload):
    headers = {**auth_headers, "Idempotency-Key": "replay-1"}
    first = await client.post("/payments", json=payment_payload, headers=headers)
    second = await client.post("/payments", json=payment_payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["transaction_id"] == second.json()["transaction_id"]


@pytest.mark.asyncio
async def test_idempotency_key_cannot_be_reused_for_new_payload(
    client, auth_headers, payment_payload
):
    headers = {**auth_headers, "Idempotency-Key": "conflict-1"}
    await client.post("/payments", json=payment_payload, headers=headers)
    payment_payload["amount"] = "1300.00"
    response = await client.post("/payments", json=payment_payload, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_high_value_payment_is_rejected(client, auth_headers, payment_payload):
    payment_payload["amount"] = "50000.01"
    response = await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "high-risk"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "REJECTED"
    assert response.json()["risk_score"] == 50


@pytest.mark.asyncio
async def test_missing_account_is_rejected(client, auth_headers, payment_payload):
    payment_payload["receiver_id"] = 999
    response = await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "missing-account"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_sender_and_receiver_must_differ(client, auth_headers, payment_payload):
    payment_payload["receiver_id"] = 101
    response = await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "same-account"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "SAME_SENDER_RECEIVER"


@pytest.mark.asyncio
async def test_invalid_amount_has_consistent_error(client, auth_headers, payment_payload):
    payment_payload["amount"] = "0"
    response = await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "bad-amount"},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_unknown_payment_returns_404(client, auth_headers):
    response = await client.get("/payments/pay_unknown", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"] == "PAYMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_list_payments_is_paginated(client, auth_headers, payment_payload):
    await client.post(
        "/payments",
        json=payment_payload,
        headers={**auth_headers, "Idempotency-Key": "list-1"},
    )
    response = await client.get("/payments?limit=10&offset=0", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1
