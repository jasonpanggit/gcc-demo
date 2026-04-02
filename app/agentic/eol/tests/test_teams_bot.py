"""Regression tests for Teams bot message handling and conversation memory."""

import sys
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import pytest
import pytest_asyncio

from api import teams_bot


_HTML_RESPONSE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Virtual Machines</title>
<style>
body { font-family: Arial, sans-serif; }
.count { font-weight: 600; }
</style>
</head>
<body>
<h3>Virtual Machines</h3>
<div class="meta">
  <div><span class="small">VM count:</span> <span class="count">2</span></div>
</div>
<table>
  <thead>
    <tr><th>Machine</th><th>OS</th></tr>
  </thead>
  <tbody>
    <tr><td>vm-01</td><td>Ubuntu</td></tr>
    <tr><td>vm-02</td><td>Windows Server</td></tr>
  </tbody>
</table>
</body>
</html>
"""


def _make_activity(conversation_id: str, text: str) -> dict[str, object]:
    return {
        "type": "message",
        "id": f"activity-{conversation_id}",
        "conversation": {"id": conversation_id},
        "from": {"id": "user-123", "name": "Test User"},
        "text": text,
        "serviceUrl": "https://smba.trafficmanager.net/test/",
        "channelId": "msteams",
    }


@pytest.fixture(autouse=True)
def clear_conversation_state():
    teams_bot._conversation_states.clear()
    yield
    teams_bot._conversation_states.clear()


@pytest_asyncio.fixture
async def teams_client():
    app = FastAPI()
    app.include_router(teams_bot.router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def test_update_conversation_history_strips_rendered_html_from_assistant_response() -> None:
    teams_bot._update_conversation_history(
        conversation_id="conv-html",
        user_message="show my virtual machines",
        assistant_response=_HTML_RESPONSE,
    )

    history = teams_bot._get_conversation_history("conv-html")

    assert history[0]["text"] == "show my virtual machines"
    assert len(history) == 2

    assistant_text = history[1]["text"]
    assert "Virtual Machines" in assistant_text
    assert "VM count:" in assistant_text
    assert "vm-01" in assistant_text
    assert "vm-02" in assistant_text
    assert "font-family" not in assistant_text
    assert "<html" not in assistant_text.lower()
    assert "<table" not in assistant_text.lower()


def test_format_conversation_context_sanitizes_existing_html_assistant_history() -> None:
    history = [
        {"role": "user", "text": "show my virtual machines"},
        {"role": "assistant", "text": _HTML_RESPONSE},
    ]

    context = teams_bot._format_conversation_context(history)

    assert "User: show my virtual machines" in context
    assert "Virtual Machines" in context
    assert "vm-01" in context
    assert "font-family" not in context
    assert "<!DOCTYPE html>" not in context
    assert "<table" not in context.lower()


def test_update_conversation_history_preserves_user_messages_with_angle_brackets() -> None:
    user_message = "How do I filter on <resourceGroup> names?"

    teams_bot._update_conversation_history(
        conversation_id="conv-user-text",
        user_message=user_message,
        assistant_response="Use a resource group filter.",
    )

    history = teams_bot._get_conversation_history("conv-user-text")

    assert history[0]["text"] == user_message
    assert history[1]["text"] == "Use a resource group filter."


def test_normalize_assistant_text_preserves_inline_tag_examples() -> None:
    assistant_text = "Use the <div> tag as an HTML container example."

    assert teams_bot._normalize_assistant_text(assistant_text) == assistant_text


def test_normalize_assistant_text_preserves_xml_like_error_messages() -> None:
    assistant_text = "Errors detected:\n<error code='E001'>\n<error code='E002'>"

    assert teams_bot._normalize_assistant_text(assistant_text) == assistant_text


def test_normalize_assistant_text_handles_parser_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_parser_error(*_args, **_kwargs):
        raise RuntimeError("parser failure")

    monkeypatch.setattr(teams_bot, "BeautifulSoup", raise_parser_error)

    normalized = teams_bot._normalize_assistant_text(_HTML_RESPONSE)

    assert "Virtual Machines" in normalized
    assert "vm-01" in normalized
    assert "<!DOCTYPE html>" not in normalized


def test_large_html_response_uses_fallback_text_and_skips_adaptive_card() -> None:
    large_html = f"<html><body><table><tr><th>Machine</th></tr><tr><td>{'x' * (teams_bot._MAX_HTML_RESPONSE_SIZE + 32)}</td></tr></table></body></html>"

    normalized = teams_bot._normalize_assistant_text(large_html)
    payload = teams_bot.create_html_adaptive_card_response(large_html)

    assert "Machine" in normalized
    assert "<table" not in normalized.lower()
    assert payload is None


def test_create_html_adaptive_card_response_preserves_table_structure() -> None:
    payload = teams_bot.create_html_adaptive_card_response(_HTML_RESPONSE)

    assert payload is not None
    assert "text" not in payload
    assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"

    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    assert any(item.get("type") == "Table" for item in card["body"])

    table = next(item for item in card["body"] if item.get("type") == "Table")
    header_cells = table["rows"][0]["cells"]
    first_data_row = table["rows"][1]["cells"]

    assert header_cells[0]["items"][0]["text"] == "Machine"
    assert first_data_row[0]["items"][0]["text"] == "vm-01"
    assert first_data_row[1]["items"][0]["text"] == "Ubuntu"


def test_create_html_adaptive_card_response_requests_full_width_for_wide_tables() -> None:
        payload = teams_bot.create_html_adaptive_card_response(
                """
                <html>
                <body>
                <h3>OS Inventory</h3>
                <table>
                    <thead>
                        <tr><th>Machine</th><th>Resource Group</th><th>Location</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>vm-01</td><td>agentic-aiops-demo-rg</td><td>eastus</td></tr>
                        <tr><td>vm-02</td><td>arcgis-demo-rg</td><td>westus2</td></tr>
                    </tbody>
                </table>
                </body>
                </html>
                """
        )

        assert payload is not None

        card = payload["attachments"][0]["content"]
        assert card["msteams"] == {"width": "Full"}

        table = next(item for item in card["body"] if item.get("type") == "Table")
        widths = [column["width"] for column in table["columns"]]

        assert len(widths) == 3
        assert widths[1] > widths[0]
        assert widths[1] > widths[2]


def test_create_html_adaptive_card_response_marks_data_only_tables_correctly() -> None:
        payload = teams_bot.create_html_adaptive_card_response(
                """
                <html>
                <body>
                <h3>Instances</h3>
                <table>
                    <tbody>
                        <tr><td>vm-01</td><td>Ubuntu</td></tr>
                        <tr><td>vm-02</td><td>Windows Server</td></tr>
                    </tbody>
                </table>
                </body>
                </html>
                """
        )

        assert payload is not None

        card = payload["attachments"][0]["content"]
        table = next(item for item in card["body"] if item.get("type") == "Table")

        assert table["firstRowAsHeader"] is False


def test_create_html_adaptive_card_response_adds_compact_layout_for_wide_tables() -> None:
        payload = teams_bot.create_html_adaptive_card_response(
                """
                <html>
                <body>
                <h3>OS Inventory</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Machine</th>
                            <th>OS</th>
                            <th>Version</th>
                            <th>Type</th>
                            <th>Resource Group</th>
                            <th>Location</th>
                            <th>Source</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>WIN-JBC7MM2NO8J</td>
                            <td>Windows Server</td>
                            <td>2016</td>
                            <td>Windows</td>
                            <td>agentic-aiops-demo-rg</td>
                            <td>eastus</td>
                            <td>log_analytics_heartbeat</td>
                        </tr>
                    </tbody>
                </table>
                </body>
                </html>
                """
        )

        assert payload is not None

        card = payload["attachments"][0]["content"]
        table = next(item for item in card["body"] if item.get("type") == "Table")
        compact_container = next(
            item
            for item in card["body"]
            if item.get("type") == "Container" and item.get("targetWidth") == "atMost:standard"
        )

        assert table["targetWidth"] == "atLeast:wide"
        assert compact_container["targetWidth"] == "atMost:standard"

        first_record = compact_container["items"][0]

        assert first_record["items"][0]["text"] == "WIN-JBC7MM2NO8J"
        assert first_record["items"][1]["type"] == "FactSet"
        assert first_record["items"][1]["facts"][0] == {"title": "OS", "value": "Windows Server"}


@pytest.mark.asyncio
async def test_handle_teams_bot_message_sends_adaptive_card_and_stores_plain_text(
    teams_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAMS_BOT_APP_ID", "bot-id")
    monkeypatch.setenv("TEAMS_BOT_APP_PASSWORD", "bot-secret")

    captured: dict[str, object] = {}

    class FakeOrchestrator:
        async def process_message(self, message: str) -> dict[str, object]:
            captured["prompt"] = message
            return {"success": True, "response": _HTML_RESPONSE}

    async def fake_get_mcp_orchestrator() -> FakeOrchestrator:
        return FakeOrchestrator()

    async def fake_send_typing_indicator(**_kwargs) -> bool:
        return True

    async def fake_send_teams_response(*, response_text: str, response_payload=None, **_kwargs) -> bool:
        captured["sent_text"] = response_text
        captured["sent_payload"] = response_payload
        return True

    monkeypatch.setitem(
        sys.modules,
        "agents.mcp_orchestrator",
        SimpleNamespace(get_mcp_orchestrator=fake_get_mcp_orchestrator),
    )
    monkeypatch.setattr(teams_bot, "send_typing_indicator", fake_send_typing_indicator)
    monkeypatch.setattr(teams_bot, "send_teams_response", fake_send_teams_response)

    response = await teams_client.post(
        "/api/teams-bot/messages",
        json=_make_activity("conv-send", "show my virtual machines"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    sent_text = captured["sent_text"]
    assert "Virtual Machines" in sent_text
    assert "vm-01" in sent_text
    assert "font-family" not in sent_text
    assert "<!DOCTYPE html>" not in sent_text
    assert "<table" not in sent_text.lower()

    sent_payload = captured["sent_payload"]
    assert sent_payload is not None
    assert "text" not in sent_payload
    assert sent_payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"

    card = sent_payload["attachments"][0]["content"]
    assert any(item.get("type") == "Table" for item in card["body"])

    history = teams_bot._get_conversation_history("conv-send")
    assert history[1]["text"] == sent_text


@pytest.mark.asyncio
async def test_send_teams_response_omits_top_level_text_for_adaptive_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self, status: int, payload: dict[str, object] | None = None, text: str = "") -> None:
            self.status = status
            self._payload = payload or {}
            self._text = text

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def json(self) -> dict[str, object]:
            return self._payload

        async def text(self) -> str:
            return self._text

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            if "oauth2" in url:
                return FakeResponse(200, {"access_token": "token-123"})

            captured["reply_url"] = url
            captured["reply_body"] = kwargs["json"]
            return FakeResponse(201)

    monkeypatch.setattr(teams_bot.aiohttp, "ClientSession", FakeClientSession)

    response_payload = teams_bot.create_html_adaptive_card_response(_HTML_RESPONSE)

    assert response_payload is not None

    sent = await teams_bot.send_teams_response(
        service_url="https://smba.trafficmanager.net/test",
        conversation_id="conv-card",
        activity_id="activity-card",
        response_text=teams_bot._normalize_assistant_text(_HTML_RESPONSE),
        bot_id="bot-id",
        bot_password="bot-secret",
        response_payload=response_payload,
    )

    assert sent is True
    assert captured["reply_url"].endswith("/v3/conversations/conv-card/activities/activity-card")

    reply_body = captured["reply_body"]
    assert "text" not in reply_body
    assert reply_body["from"]["id"] == "bot-id"
    assert reply_body["replyToId"] == "activity-card"
    assert reply_body["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"


@pytest.mark.asyncio
async def test_follow_up_prompt_uses_sanitized_assistant_history(
    teams_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAMS_BOT_APP_ID", "bot-id")
    monkeypatch.setenv("TEAMS_BOT_APP_PASSWORD", "bot-secret")

    prompts: list[str] = []

    class FakeOrchestrator:
        async def process_message(self, message: str) -> dict[str, object]:
            prompts.append(message)
            if len(prompts) == 1:
                return {"success": True, "response": _HTML_RESPONSE}
            return {"success": True, "response": "No SolarWinds entries were found."}

    async def fake_get_mcp_orchestrator() -> FakeOrchestrator:
        return FakeOrchestrator()

    async def fake_send_typing_indicator(**_kwargs) -> bool:
        return True

    async def fake_send_teams_response(**_kwargs) -> bool:
        return True

    monkeypatch.setitem(
        sys.modules,
        "agents.mcp_orchestrator",
        SimpleNamespace(get_mcp_orchestrator=fake_get_mcp_orchestrator),
    )
    monkeypatch.setattr(teams_bot, "send_typing_indicator", fake_send_typing_indicator)
    monkeypatch.setattr(teams_bot, "send_teams_response", fake_send_teams_response)

    first_response = await teams_client.post(
        "/api/teams-bot/messages",
        json=_make_activity("conv-follow-up", "show my virtual machines"),
    )
    second_response = await teams_client.post(
        "/api/teams-bot/messages",
        json=_make_activity("conv-follow-up", "Do I have SolarWinds in my software inventory?"),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert len(prompts) == 2

    second_prompt = prompts[1]
    assert "Here is our conversation history for context:" in second_prompt
    assert "Virtual Machines" in second_prompt
    assert "vm-01" in second_prompt
    assert "font-family" not in second_prompt
    assert "<!DOCTYPE html>" not in second_prompt
    assert "<table" not in second_prompt.lower()
    assert "Current user message: Do I have SolarWinds in my software inventory?" in second_prompt


@pytest.mark.asyncio
async def test_handle_teams_bot_message_stores_error_response_in_history(
    teams_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEAMS_BOT_APP_ID", "bot-id")
    monkeypatch.setenv("TEAMS_BOT_APP_PASSWORD", "bot-secret")

    class FakeOrchestrator:
        async def process_message(self, message: str) -> dict[str, object]:
            return {"success": False, "error": "backend unavailable"}

    async def fake_get_mcp_orchestrator() -> FakeOrchestrator:
        return FakeOrchestrator()

    async def fake_send_typing_indicator(**_kwargs) -> bool:
        return True

    async def fake_send_teams_response(**_kwargs) -> bool:
        return True

    monkeypatch.setitem(
        sys.modules,
        "agents.mcp_orchestrator",
        SimpleNamespace(get_mcp_orchestrator=fake_get_mcp_orchestrator),
    )
    monkeypatch.setattr(teams_bot, "send_typing_indicator", fake_send_typing_indicator)
    monkeypatch.setattr(teams_bot, "send_teams_response", fake_send_teams_response)

    response = await teams_client.post(
        "/api/teams-bot/messages",
        json=_make_activity("conv-error", "show my virtual machines"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "error"

    history = teams_bot._get_conversation_history("conv-error")
    assert history[0]["text"] == "show my virtual machines"
    assert history[1]["text"] == "❌ Error: backend unavailable"