"""Focused contract regressions for alert action API normalization."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api.alerts import router as alerts_router


class FakeLoadedAlertConfiguration:
    def __init__(self, recipients=None, teams_enabled=True):
        self.email_recipients = recipients or []
        self.teams_settings = SimpleNamespace(enabled=teams_enabled)

    def dict(self):
        return {
            "enabled": True,
            "critical": {"period": 3, "unit": "months", "frequency": "weekly"},
            "warning": {"period": 6, "unit": "months", "frequency": "monthly"},
            "info": {"period": 12, "unit": "months", "frequency": "quarterly"},
            "email_recipients": list(self.email_recipients),
            "smtp_settings": {
                "server": "smtp.gmail.com",
                "port": 587,
                "use_tls": True,
                "username": "alerts@example.com",
                "password": "secret",
            },
            "teams_settings": {"enabled": self.teams_settings.enabled},
        }


class FakeSMTPSettings:
    def __init__(self, **kwargs):
        self.enabled = kwargs.get("enabled", True)
        self.server = kwargs.get("server", "smtp.gmail.com")
        self.port = kwargs.get("port", 587)
        self.username = kwargs.get("username", "alerts@example.com")
        self.password = kwargs.get("password", "secret")
        self.use_tls = kwargs.get("use_tls", True)
        self.use_ssl = kwargs.get("use_ssl", False)
        self.from_email = kwargs.get("from_email", "alerts@example.com")
        self.from_name = kwargs.get("from_name", "Alert System")

    def is_gmail_config(self):
        return "gmail.com" in self.server


class FakeAlertConfiguration:
    def __init__(self, **kwargs):
        self._payload = dict(kwargs)
        smtp_settings = self._payload.get("smtp_settings", {})
        self.smtp_settings = SimpleNamespace(password=smtp_settings.get("password", ""))

    def dict(self):
        return dict(self._payload)


class FakeAlertPreviewItem:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def dict(self):
        return dict(self.__dict__)


class FakeAlertManager:
    def __init__(self, recipients=None, teams_enabled=True, send_success=True, smtp_success=True, teams_success=True):
        self._config = FakeLoadedAlertConfiguration(recipients=recipients, teams_enabled=teams_enabled)
        self._send_success = send_success
        self._smtp_success = smtp_success
        self._teams_success = teams_success

    async def load_configuration(self):
        if self._config is None:
            self._config = FakeLoadedAlertConfiguration(recipients=["ops@example.com"], teams_enabled=True)
        return self._config

    async def save_configuration(self, config):
        self._config = config
        return True

    async def test_smtp_connection(self, _smtp_settings):
        if self._smtp_success:
            return True, "SMTP connection successful"
        return False, "SMTP connection failed"

    async def send_alert(self, **_kwargs):
        return self._send_success

    async def send_alert_teams(self, *_args, **_kwargs):
        if self._teams_success:
            return True, "Teams alert sent successfully"
        return False, "Teams alert failed"


@pytest_asyncio.fixture
async def alerts_contract_client():
    app = FastAPI()
    app.include_router(alerts_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def _install_alert_manager(monkeypatch, manager):
    monkeypatch.setitem(
        sys.modules,
        "utils.alert_manager",
        SimpleNamespace(
            alert_manager=manager,
            AlertConfiguration=FakeAlertConfiguration,
            SMTPSettings=FakeSMTPSettings,
            AlertPreviewItem=FakeAlertPreviewItem,
        ),
    )


@pytest.mark.asyncio
async def test_send_test_alert_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    _install_alert_manager(monkeypatch, FakeAlertManager(send_success=True))

    response = await alerts_contract_client.post(
        "/api/alerts/send",
        json={
            "recipients": ["admin@example.com", "ops@example.com"],
            "level": "info",
            "custom_subject": "Alert test",
            "custom_body": "Hello",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["recipients_count"] == 2
    assert body["data"]["recipients"] == ["admin@example.com", "ops@example.com"]
    assert body["data"]["subject"] == "Alert test"


@pytest.mark.asyncio
async def test_get_alert_configuration_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    _install_alert_manager(monkeypatch, FakeAlertManager(recipients=["ops@example.com"]))

    response = await alerts_contract_client.get("/api/alerts/config")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["source"] == "cosmos"
    assert body["data"]["configuration"]["email_recipients"] == ["ops@example.com"]
    assert body["data"]["configuration"]["smtp_settings"]["password"] == "***"


@pytest.mark.asyncio
async def test_reload_alert_configuration_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    _install_alert_manager(monkeypatch, FakeAlertManager(recipients=["ops@example.com"]))

    response = await alerts_contract_client.post("/api/alerts/config/reload")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["message"] == "Configuration reloaded successfully from Cosmos DB"
    assert body["data"]["configuration"]["smtp_settings"]["password"] == "***"


@pytest.mark.asyncio
async def test_save_alert_configuration_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    _install_alert_manager(monkeypatch, FakeAlertManager(recipients=["ops@example.com"]))

    response = await alerts_contract_client.post(
        "/api/alerts/config",
        json={
            "enabled": True,
            "email_recipients": ["admin@example.com"],
            "smtp_settings": {
                "server": "smtp.gmail.com",
                "port": 587,
                "username": "alerts@example.com",
                "password": "new-secret",
                "use_tls": True,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["message"] == "Configuration saved successfully"
    assert body["data"]["configuration"]["smtp_settings"]["password"] == "***"
    assert body["data"]["configuration"]["email_recipients"] == ["admin@example.com"]


@pytest.mark.asyncio
async def test_send_test_alert_failure_returns_error_contract(alerts_contract_client, monkeypatch):
    _install_alert_manager(monkeypatch, FakeAlertManager(send_success=False))

    response = await alerts_contract_client.post(
        "/api/alerts/send",
        json={
            "recipients": ["admin@example.com"],
            "level": "info",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["count"] == 0
    assert body["error"] == "Failed to send test alert"
    assert body["message"] == "Check SMTP configuration and logs"


@pytest.mark.asyncio
async def test_send_teams_bot_notification_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    monkeypatch.setenv("TEAMS_BOT_APP_ID", "bot-id")
    monkeypatch.setenv("TEAMS_BOT_APP_PASSWORD", "bot-secret")

    class FakeResponse:
        def __init__(self, status, payload=None, text=""):
            self.status = status
            self._payload = payload or {}
            self._text = text

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return self._payload

        async def text(self):
            return self._text

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **_kwargs):
            if "oauth2" in url:
                return FakeResponse(200, {"access_token": "token-123"})
            return FakeResponse(201, {"id": "activity-1"})

    monkeypatch.setitem(sys.modules, "aiohttp", SimpleNamespace(ClientSession=FakeClientSession))
    _install_alert_manager(monkeypatch, FakeAlertManager())

    response = await alerts_contract_client.post(
        "/api/alerts/send-teams-bot-notification",
        params={"alert_level": "critical", "conversation_id": "conv-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 1
    assert isinstance(body["data"], dict)
    assert body["data"]["alert_level"] == "critical"
    assert body["data"]["notification_sent"] is True
    assert body["data"]["target"] == "conversation conv-123"


@pytest.mark.asyncio
async def test_teams_bot_conversations_returns_wrapped_object_payload(alerts_contract_client, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "api.teams_bot",
        SimpleNamespace(
            _conversation_states={
                "conv-123": {
                    "history": [{"text": "hello"}],
                    "last_updated": datetime.utcnow() - timedelta(minutes=15),
                },
                "conv-456": {
                    "history": [{"text": "hi"}, {"text": "again"}],
                    "last_updated": datetime.utcnow() - timedelta(minutes=5),
                }
            }
        ),
    )

    response = await alerts_contract_client.get("/api/alerts/teams-bot-conversations")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["count"] == 2
    assert isinstance(body["data"], dict)
    assert body["data"]["total_conversations"] == 2
    assert body["data"]["conversations"][0]["conversation_id"] == "conv-456"