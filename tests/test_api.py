import json

import httpx

from app.ai.client import AnthropicClient, MockAIClient, parse_analysis
from app.config import Settings
from app.security import woocommerce_signature

LEAD = {
    "source": "web_form",
    "external_id": "form-1",
    "customer_name": "María López",
    "customer_email": "maria@example.com",
    "message": "Hola, quiero reservar el Day Pass para 4 personas este sábado",
}

WC_ORDER = {
    "id": 5001,
    "number": "5001",
    "billing": {"first_name": "John", "last_name": "Smith", "email": "john@example.com"},
    "line_items": [{"name": "Day Pass Adulto", "quantity": 2}],
    "customer_note": "I have a complaint, I need a refund for my last visit",
}


# ---------- Salud y seguridad ----------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["database"] is True
    assert "x-request-id" in r.headers


def test_requires_api_key(client):
    assert client.get("/api/v1/leads").status_code == 401
    assert client.get("/api/v1/leads", headers={"X-API-Key": "wrong"}).status_code == 401


# ---------- REST ----------

def test_create_lead_is_enriched_by_ai(client, auth):
    r = client.post("/api/v1/leads", json=LEAD, headers=auth)
    assert r.status_code == 201
    body = r.json()
    assert body["intent"] == "booking"
    assert body["priority"] == "high"
    assert body["status"] == "new"


def test_create_lead_is_idempotent(client, auth):
    first = client.post("/api/v1/leads", json=LEAD, headers=auth)
    second = client.post("/api/v1/leads", json=LEAD, headers=auth)
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/v1/leads", headers=auth).json()) == 1


def test_validation_error(client, auth):
    r = client.post("/api/v1/leads", json={**LEAD, "customer_email": "not-an-email"}, headers=auth)
    assert r.status_code == 422


def test_filter_and_update_status(client, auth):
    lead_id = client.post("/api/v1/leads", json=LEAD, headers=auth).json()["id"]
    client.post("/api/v1/leads", json={**LEAD, "external_id": "form-2", "message": "¿Cuánto cuesta?"}, headers=auth)

    booking = client.get("/api/v1/leads?intent=booking", headers=auth).json()
    assert [lead["id"] for lead in booking] == [lead_id]

    r = client.patch(f"/api/v1/leads/{lead_id}", json={"status": "won"}, headers=auth)
    assert r.json()["status"] == "won"
    assert client.patch("/api/v1/leads/999", json={"status": "won"}, headers=auth).status_code == 404


# ---------- Webhook WooCommerce ----------

def _signed(payload: dict, secret: str = "wc-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-WC-Webhook-Signature": woocommerce_signature(body, secret), "X-WC-Webhook-Topic": "order.created", "Content-Type": "application/json"}


def test_woocommerce_webhook_valid_signature(client, auth):
    body, headers = _signed(WC_ORDER)
    r = client.post("/webhooks/woocommerce", content=body, headers=headers)
    assert r.status_code == 202
    assert r.json()["status"] == "created"

    lead = client.get(f"/api/v1/leads/{r.json()['lead_id']}", headers=auth).json()
    assert lead["source"] == "woocommerce"
    assert lead["customer_name"] == "John Smith"
    assert lead["intent"] == "complaint"
    assert lead["language"] == "en"

    # WooCommerce puede reenviar el mismo evento: no debe duplicarse
    assert client.post("/webhooks/woocommerce", content=body, headers=headers).json()["status"] == "duplicate"


def test_woocommerce_webhook_rejects_bad_signature(client):
    body, headers = _signed(WC_ORDER, secret="attacker-secret")
    assert client.post("/webhooks/woocommerce", content=body, headers=headers).status_code == 401


def test_woocommerce_ping(client):
    r = client.post("/webhooks/woocommerce", content=b"webhook_id=12", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.json() == {"status": "ping_ok"}


# ---------- GraphQL ----------

def test_graphql_query_and_mutation(client, auth):
    lead_id = client.post("/api/v1/leads", json=LEAD, headers=auth).json()["id"]

    q = {"query": "{ leads(intent: \"booking\") { id customerName intent priority } }"}
    r = client.post("/graphql", json=q, headers=auth)
    assert r.status_code == 200
    assert r.json()["data"]["leads"][0] == {"id": lead_id, "customerName": "María López", "intent": "booking", "priority": "high"}

    m = {"query": f"mutation {{ updateLeadStatus(id: {lead_id}, status: \"contacted\") {{ id status }} }}"}
    assert client.post("/graphql", json=m, headers=auth).json()["data"]["updateLeadStatus"]["status"] == "contacted"


def test_graphql_requires_api_key(client):
    assert client.post("/graphql", json={"query": "{ leads { id } }"}).status_code == 401


# ---------- Cliente de IA ----------

def test_parse_analysis_tolerates_extra_text():
    raw = 'Claro, aquí está: {"intent": "pricing", "priority": "low", "language": "es", "summary": "Pide precios"}'
    assert parse_analysis(raw).intent == "pricing"


def test_ai_falls_back_when_response_is_invalid():
    class BrokenAI(MockAIClient):
        def _complete(self, message):
            return '{"intent": "something-invalid"}'

    result = BrokenAI().analyze("hola")
    assert result.intent == "other"  # no rompe el flujo


def test_anthropic_client_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(529, json={"error": "overloaded"})
        text = json.dumps({"intent": "booking", "priority": "high", "language": "es", "summary": "Reserva"})
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})

    settings = Settings(ai_provider="anthropic", ai_api_key="k", ai_max_retries=2)
    ai = AnthropicClient(settings, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert ai.analyze("Quiero reservar").intent == "booking"
    assert calls["n"] == 2


def test_anthropic_client_does_not_retry_on_auth_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"error": "invalid key"})

    settings = Settings(ai_provider="anthropic", ai_api_key="bad", ai_max_retries=3)
    ai = AnthropicClient(settings, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert ai.analyze("hola").intent == "other"  # fallback
    assert calls["n"] == 1
