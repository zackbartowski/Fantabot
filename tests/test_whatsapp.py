from __future__ import annotations

import pytest

from app.whatsapp.client import WhatsAppClient

PHONE_NUMBER_ID = "1234567890"
API_VERSION = "v21.0"
URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"


@pytest.fixture
def client() -> WhatsAppClient:
    return WhatsAppClient(
        access_token="fake-token",
        phone_number_id=PHONE_NUMBER_ID,
        api_version=API_VERSION,
    )


def test_send_text_success(requests_mock, client: WhatsAppClient):
    requests_mock.post(URL, json={"messages": [{"id": "wamid.1"}]}, status_code=200)

    results = client.send_text_to_all(["393331234567"], "ciao")

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].recipient == "393331234567"


def test_send_text_multiple_recipients(requests_mock, client: WhatsAppClient):
    requests_mock.post(URL, json={"messages": [{"id": "wamid.1"}]}, status_code=200)

    results = client.send_text_to_all(["3931111111", "3932222222"], "ciao")

    assert len(results) == 2
    assert all(r.success for r in results)
    assert requests_mock.call_count == 2


def test_send_text_non_recoverable_error_no_retry(requests_mock, client: WhatsAppClient):
    requests_mock.post(
        URL,
        json={"error": {"message": "Invalid token"}},
        status_code=401,
    )

    results = client.send_text_to_all(["393331234567"], "ciao")

    assert results[0].success is False
    assert "http_401" in results[0].error
    assert requests_mock.call_count == 1


def test_send_text_retries_on_server_error_then_succeeds(requests_mock, client: WhatsAppClient):
    requests_mock.post(
        URL,
        [
            {"json": {"error": {"message": "temp"}}, "status_code": 503},
            {"json": {"messages": [{"id": "wamid.1"}]}, "status_code": 200},
        ],
    )

    results = client.send_text_to_all(["393331234567"], "ciao")

    assert results[0].success is True
    assert requests_mock.call_count == 2


def test_dry_run_does_not_call_api(requests_mock):
    dry_client = WhatsAppClient(
        access_token="", phone_number_id="", api_version=API_VERSION, dry_run=True
    )
    results = dry_client.send_text_to_all(["393331234567"], "ciao")

    assert results[0].success is True
    assert results[0].dry_run is True
    assert requests_mock.call_count == 0


def test_requires_credentials_unless_dry_run():
    with pytest.raises(ValueError):
        WhatsAppClient(access_token="", phone_number_id="", dry_run=False)
