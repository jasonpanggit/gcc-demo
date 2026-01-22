"""
Microsoft Agent Framework inventory assistant orchestrator for the EOL demo experience.

This module replaces the legacy multi-agent implementation with a lightweight
orchestrator built on the Microsoft Agent Framework preview package. It keeps
the public interface expected by the FastAPI layer while simplifying the
internal flow to rely on a single assistant agent backed by Azure OpenAI.
"""
from __future__ import annotations

import asyncio
import html
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from agent_framework.azure import AzureOpenAIChatClient as AzureOpenAIChatClientType  # type: ignore[import]
    from azure.identity import DefaultAzureCredential as DefaultAzureCredentialType  # type: ignore[import]
else:
    AzureOpenAIChatClientType = Any
    DefaultAzureCredentialType = Any

try:
    from agent_framework import ChatMessage, ChatResponse  # type: ignore[import]
    _AGENT_FRAMEWORK_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _AGENT_FRAMEWORK_AVAILABLE = False

    @dataclass
    class ChatMessage:  # type: ignore[no-redef]
        role: str
        text: str

    @dataclass
    class ChatResponse:  # type: ignore[no-redef]
        messages: List[ChatMessage]
        content: Optional[str] = None

try:
    from agent_framework.azure import AzureOpenAIChatClient  # type: ignore[import]
    _AGENT_FRAMEWORK_CHAT_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    AzureOpenAIChatClient = None  # type: ignore[assignment]
    _AGENT_FRAMEWORK_CHAT_AVAILABLE = False

try:
    from azure.identity import DefaultAzureCredential  # type: ignore[import]
    _DEFAULT_CREDENTIAL_AVAILABLE = True
except ModuleNotFoundError:
    DefaultAzureCredential = None  # type: ignore[assignment]
    _DEFAULT_CREDENTIAL_AVAILABLE = False

from utils import get_logger, config, QueryPatterns, extract_software_name_and_version
from utils.cache_stats_manager import cache_stats_manager
from utils.agent_framework_clients import build_chat_options, create_chat_client

logger = get_logger(__name__)


class InventoryAssistantOrchestrator:
    """High-level inventory assistant orchestrator powered by Microsoft Agent Framework."""

    _SYSTEM_PROMPT_TEMPLATE = """You are the End-of-Life (EOL) modernization assistant for enterprise IT teams.
Use the provided organizational context, inventory insights, and Azure service
status to respond with accurate, actionable guidance. When the context does not
contain the requested data, clearly explain the gap and suggest verification
steps.

Always respond using HTML markup:
- Summaries belong in <section> elements with headings (<h2>, <h3>).
- Render tabular data with semantic <table>, <thead>, and <tbody> tags.
- Use <p> for narrative text, <ul><li> for bullet points, and include brief
   explanations alongside any metrics.
- Avoid Markdown entirely and do not return raw JSON.
- When citing data, reference the source (inventory cache, live query, or agent) or state when data is unavailable.

Context:
{context}

Guidelines:
1. Keep responses concise but specific to the user's environment.
2. Highlight critical EOL risks and recommend remediation steps.
3. Surface relevant inventory metrics or Azure configuration insights when they
   strengthen the answer.
4. When uncertain, state any assumptions and provide next steps for validation.
"""

    _DECLINED_CONFIRMATION_MESSAGE = (
        "I understand you've decided not to proceed with that action. Let me know "
        "how else I can help with inventory insights, EOL research, or upgrade "
        "planning."
    )

    def __init__(self) -> None:
        self.agent_name = "inventory_assistant"
        self.session_id = f"maf-inventory-asst-{uuid.uuid4()}"
        self.conversation_history: List[Dict[str, Any]] = []
        self.agent_interaction_logs: List[Dict[str, Any]] = []
        self.orchestrator_logs: List[Dict[str, Any]] = []
        self._context_cache: Dict[str, Any] = {"value": None, "timestamp": 0.0}
        self._context_ttl_seconds = 60.0
        self._lock = asyncio.Lock()

        self._default_credential: Optional[DefaultAzureCredentialType] = None
        self._chat_client: Optional[AzureOpenAIChatClientType] = None

        if not _AGENT_FRAMEWORK_AVAILABLE:
            logger.warning(
                "⚠️ Microsoft Agent Framework core package not installed; inventory assistant requests will return fallback responses"
            )
        elif not _AGENT_FRAMEWORK_CHAT_AVAILABLE:
            logger.warning(
                "⚠️ Microsoft Agent Framework Azure extras not installed; inventory assistant requests will return fallback responses"
            )

        self._chat_client = self._create_chat_client()

        logger.info("✅ Microsoft Agent Framework inventory assistant orchestrator initialized")

    # ------------------------------------------------------------------
    # Public API expected by FastAPI routes
    # ------------------------------------------------------------------

    async def respond_with_confirmation(
        self,
        message: str,
        *,
        confirmed: bool = False,
        original_message: Optional[str] = None,
        timeout_seconds: int = 120,
    ) -> Dict[str, Any]:
        """Process an inventory assistant request with optional confirmation semantics."""

        async with self._lock:
            if not confirmed and original_message is None:
                self.session_id = f"maf-inventory-asst-{uuid.uuid4()}"

            start_time = time.time()
            conversation_id = len(self.conversation_history) + 1
            self._log_event(
                "assistant_with_confirmation_start",
                {
                    "conversation_id": conversation_id,
                    "confirmed": confirmed,
                    "has_original": original_message is not None,
                    "timeout_seconds": timeout_seconds,
                },
            )

            # Handle confirmation response paths first
            if confirmed and original_message:
                user_message = original_message
                confirmation_state = "confirmed"
            elif not confirmed and original_message:
                response_payload = self._build_declined_confirmation_response(
                    user_message=message,
                    original_message=original_message,
                    conversation_id=conversation_id,
                    started_at=start_time,
                )
                self._log_event(
                    "assistant_with_confirmation_declined",
                    {"conversation_id": conversation_id, "original_message": original_message},
                )
                return response_payload
            else:
                user_message = message
                confirmation_state = "initial_request"

            self._append_agent_communication(
                role="user",
                content=user_message,
                conversation_id=conversation_id,
                metadata={
                    "confirmed": confirmed,
                    "confirmation_state": confirmation_state,
                    "original_message": original_message,
                },
            )

            agent_grounding: Dict[str, Any] = {
                "insights": "",
                "metadata": {},
                "agents_called": [],
            }

            if not await self._ensure_chat_client():
                logger.warning("⚠️ AzureOpenAIChatClient unavailable, returning fallback response")
                return self._fallback_response(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    started_at=start_time,
                    error="AzureOpenAIChatClient unavailable",
                    agent_metadata=agent_grounding["metadata"],
                    agents_called=agent_grounding["agents_called"],
                )

            context = await self._build_chat_context()
            agent_grounding = await self._gather_agent_grounding(
                user_message=user_message,
                conversation_id=conversation_id,
            )
            system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(context=context)
            if agent_grounding.get("insights"):
                system_prompt = f"{system_prompt}\n\nLive Agent Insights:\n{agent_grounding['insights']}"

            messages = [
                ChatMessage(role="system", text=system_prompt),
                ChatMessage(role="user", text=user_message),
            ]

            try:
                chat_kwargs = build_chat_options(
                    conversation_id=self.session_id,
                    allow_multiple_tool_calls=False,
                    store=False,
                    temperature=float(os.getenv("INVENTORY_ASSISTANT_TEMPERATURE", "0.2")),
                    max_tokens=int(os.getenv("INVENTORY_ASSISTANT_MAX_TOKENS", "900")),
                )
                self._log_chat_request(chat_kwargs, context="inventory_assistant")
                response: ChatResponse = await asyncio.wait_for(
                    self._chat_client.get_response(messages=messages, **chat_kwargs),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error("❌ Inventory assistant request timed out after %ss", timeout_seconds)
                return self._fallback_response(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    started_at=start_time,
                    error=f"Timed out after {timeout_seconds} seconds",
                    agent_metadata=agent_grounding.get("metadata"),
                    agents_called=agent_grounding.get("agents_called"),
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("❌ Agent Framework inventory assistant invocation failed: %s", exc)
                return self._fallback_response(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    started_at=start_time,
                    error=str(exc),
                    agent_metadata=agent_grounding.get("metadata"),
                    agents_called=agent_grounding.get("agents_called"),
                )

            response_text = self._extract_response_text(response)
            if not response_text.strip():
                logger.warning("⚠️ Agent Framework returned empty response; synthesizing answer from agent insights")
                synthesized = self._compose_agent_summary(agent_grounding)
                if synthesized:
                    response_text = synthesized
                else:
                    response_text = (
                        "I'm sorry, I couldn't generate a response from the inventory assistant service. "
                        "Here are the latest inventory signals I gathered:\n\n"
                    )
                    fallback_summary = self._compose_agent_summary(agent_grounding, allow_empty_sections=True)
                    response_text += fallback_summary or "No additional data was available."
            else:
                appendix = self._compose_agent_appendix(agent_grounding)
                if appendix:
                    response_text = f"{response_text.strip()}\n\n---\n{appendix}"

            total_time = time.time() - start_time
            cache_stats_manager.record_agent_request(
                agent_name=self.agent_name,
                response_time_ms=total_time * 1000,
                was_cache_hit=False,
                had_error=False,
                software_name="inventory_assistant",
                version="preview",
                url="/api/inventory-assistant",
            )

            self._append_agent_communication(
                role="assistant",
                content=response_text,
                conversation_id=conversation_id,
                metadata={
                    "confirmation_state": confirmation_state,
                    "response_tokens": len(response_text.split()),
                },
            )

            result = self._build_response_payload(
                user_message=user_message,
                response_text=response_text,
                conversation_id=conversation_id,
                processing_seconds=total_time,
                confirmation_state=confirmation_state,
                error=None,
                agent_metadata=agent_grounding.get("metadata"),
                agents_called=agent_grounding.get("agents_called"),
            )

            self._log_event(
                "assistant_with_confirmation_success",
                {
                    "conversation_id": conversation_id,
                    "processing_time": total_time,
                    "confirmation_state": confirmation_state,
                },
            )
            return result

    async def get_agent_communications(self) -> List[Dict[str, Any]]:
        """Expose recent agent communications for diagnostics UI."""
        return list(self.agent_interaction_logs)

    async def clear_communications(self) -> Dict[str, Any]:
        """Reset session state and communication logs."""
        cleared_count = len(self.agent_interaction_logs)
        self.agent_interaction_logs.clear()
        self.conversation_history.clear()
        self.orchestrator_logs.clear()
        old_session = self.session_id
        self.session_id = f"maf-inventory-asst-{uuid.uuid4()}"

        self._context_cache = {"value": None, "timestamp": 0.0}
        logger.info(
            "🧹 Cleared inventory assistant communications (previous session %s, removed %d entries)",
            old_session,
            cleared_count,
        )
        return {
            "success": True,
            "cleared": cleared_count,
            "old_session_id": old_session,
            "new_session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_chat_client(self) -> bool:
        if self._chat_client:
            return True
        self._chat_client = self._create_chat_client()
        return self._chat_client is not None

    def _log_chat_request(self, chat_kwargs: Dict[str, Any], *, context: str) -> None:
        """Lightweight trace helper for Agent Framework calls."""
        try:
            logger.debug(
                "AF chat request (%s): %s",
                context,
                {k: v for k, v in chat_kwargs.items() if k != "tools"},
            )
        except Exception:
            logger.debug("AF chat request (%s) logging failed", context)

    def _create_chat_client(self) -> Optional[AzureOpenAIChatClientType]:
        """Create an AzureOpenAIChatClient using environment configuration."""
        if not _AGENT_FRAMEWORK_AVAILABLE or not _AGENT_FRAMEWORK_CHAT_AVAILABLE:
            logger.warning(
                "⚠️ Microsoft Agent Framework packages not available; chat client disabled"
            )
            return None

        client = create_chat_client()
        if client:
            logger.info("✅ AzureOpenAIChatClient ready (shared factory)")
        else:
            logger.error("❌ Failed to initialize AzureOpenAIChatClient via shared factory")
        return client

    async def _build_chat_context(self) -> str:
        now = time.time()
        cached_value = self._context_cache.get("value")
        if cached_value and now - self._context_cache.get("timestamp", 0) < self._context_ttl_seconds:
            return cached_value

        inventory_context = await self._get_inventory_summary_text()
        environment_context = self._get_environment_summary_text()

        parts = []
        if inventory_context:
            parts.append(f"Inventory Overview\n{inventory_context}")
        else:
            parts.append(
                "Inventory Overview\nNo live inventory summary is available. Ensure Azure Log Analytics is configured"
            )

        if environment_context:
            parts.append(f"Environment Signals\n{environment_context}")

        context = "\n\n".join(parts)
        self._context_cache = {"value": context, "timestamp": now}
        return context

    async def _get_inventory_summary_text(self) -> Optional[str]:
        try:
            from main import get_eol_orchestrator  # Lazy import to avoid circular dependency
        except ImportError:
            return None

        orchestrator = get_eol_orchestrator()
        inventory_agent = getattr(orchestrator, "agents", {}).get("inventory") if orchestrator else None
        if not inventory_agent:
            return None

        try:
            summary = await inventory_agent.get_inventory_summary()
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Inventory summary retrieval for context failed: %s", exc)
            return None

        if not isinstance(summary, dict):
            return None

        software_summary = summary.get("software_inventory", {})
        os_summary = summary.get("os_inventory", {})
        fragments: List[str] = []

        if isinstance(software_summary, dict) and software_summary.get("success"):
            fragments.append(
                f"Software: {software_summary.get('total_software', 0)} items on {software_summary.get('total_computers', 0)} computers"
            )
        elif isinstance(software_summary, dict) and software_summary.get("error"):
            fragments.append(f"Software summary unavailable: {software_summary.get('error')}")

        if isinstance(os_summary, dict) and os_summary.get("total_computers") is not None:
            fragments.append(
                f"OS coverage: {os_summary.get('total_computers')} computers (Windows {os_summary.get('windows_count', 0)} • Linux {os_summary.get('linux_count', 0)})"
            )

        return " | ".join(fragments) if fragments else None

    def _get_environment_summary_text(self) -> Optional[str]:
        env_summary = config.get_environment_summary() if hasattr(config, "get_environment_summary") else {}
        if not env_summary:
            return None

        sections: List[str] = []
        for key, status in env_summary.items():
            normalized = key.replace("_", " ").title()
            if key.upper() == "DEBUG_MODE":
                descriptor = "enabled" if status == "✅" else "disabled"
            else:
                descriptor = "configured" if status == "✅" else "missing"
            sections.append(f"{normalized}: {descriptor}")

        return " | ".join(sections) if sections else None
    def _compose_agent_appendix(self, agent_grounding: Dict[str, Any]) -> str:
        if not agent_grounding:
            return ""

        metadata = agent_grounding.get("metadata") if isinstance(agent_grounding, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}

        software_inventory_meta = metadata.get("software_inventory") if isinstance(metadata, dict) else {}
        if not isinstance(software_inventory_meta, dict):
            software_inventory_meta = {}

        has_software = bool(
            (software_inventory_meta.get("top_software") or [])
            or (software_inventory_meta.get("target_rows") or [])
            or software_inventory_meta.get("target_results")
        )
        has_summaries = bool(metadata.get("inventory_summary")) or bool(metadata.get("os_summary"))
        has_eol = bool(metadata.get("eol_lookup"))

        if not any([has_software, has_summaries, has_eol]):
            return ""

        appendix_sections: List[str] = []
        summary = self._compose_agent_summary(agent_grounding)
        if summary:
            appendix_sections.append("<section><h2>Inventory Insights</h2>")
            appendix_sections.append(summary)
            appendix_sections.append("</section>")

        return "".join(appendix_sections).strip()

    def _compose_agent_summary(
        self,
        agent_grounding: Dict[str, Any],
        *,
        allow_empty_sections: bool = False,
    ) -> str:
        if not agent_grounding:
            return ""

        metadata = agent_grounding.get("metadata", {}) if isinstance(agent_grounding, dict) else {}

        inventory_summary = metadata.get("inventory_summary") if isinstance(metadata, dict) else {}
        software_inventory_meta = metadata.get("software_inventory") if isinstance(metadata, dict) else {}
        if not isinstance(software_inventory_meta, dict):
            software_inventory_meta = {}
        top_software = software_inventory_meta.get("top_software") if isinstance(software_inventory_meta, dict) else []
        os_summary = metadata.get("os_summary") if isinstance(metadata, dict) else {}
        os_inventory_meta = metadata.get("os_inventory") if isinstance(metadata, dict) else {}
        if not isinstance(os_inventory_meta, dict):
            os_inventory_meta = {}
        paginated_rows_meta = os_inventory_meta.get("paginated_rows") if isinstance(os_inventory_meta.get("paginated_rows"), dict) else {}
        os_eol_checks = os_inventory_meta.get("eol_checks") if isinstance(os_inventory_meta.get("eol_checks"), dict) else {}
        eol_lookup = metadata.get("eol_lookup") if isinstance(metadata, dict) else {}
        requested_plan = metadata.get("requested_plan") if isinstance(metadata, dict) else []
        if not isinstance(requested_plan, list):
            requested_plan = []
        include_os_sections = metadata.get("include_os_sections") if isinstance(metadata, dict) else None
        if include_os_sections is None:
            include_os_sections = any(
                step in {"os_summary", "os_inventory_sample", "os_inventory_eol_checks"}
                for step in requested_plan
            )

        sections: List[str] = []
        if inventory_summary:
            software_section = inventory_summary.get("software", {})
            os_section = inventory_summary.get("os", {})

            if software_section or allow_empty_sections:
                bullets = [
                    f"<li>Software items tracked: {self._sanitize_cell(software_section.get('total_software', 0))}"
                    f" across {self._sanitize_cell(software_section.get('total_computers', 0))} computers</li>"
                ]
                publishers = software_section.get("top_publishers") or []
                section_parts = ["<section><h3>Software Inventory Snapshot</h3>"]
                section_parts.append(f"<ul>{''.join(bullets)}</ul>")
                if publishers:
                    publisher_rows = [
                        [
                            item.get("publisher", "Unknown"),
                            str(item.get("installations", 0)),
                        ]
                        for item in publishers
                    ]
                    publisher_footnote = f"Showing top {len(publishers)} publishers."
                    table = self._render_html_table(
                        ["Publisher", "Installations"],
                        publisher_rows,
                        footnote=publisher_footnote,
                        highlight_first_column=True,
                    )
                    if table:
                        section_parts.append(f"<div><h4>Top Publishers</h4>{table}</div>")
                section_parts.append("</section>")
                sections.append("".join(section_parts))

            if include_os_sections and (os_section or allow_empty_sections):
                bullets = [
                    f"<li>Computers reporting: {self._sanitize_cell(os_section.get('total_computers', 0))}</li>"
                ]
                windows_count = os_section.get("windows_count")
                linux_count = os_section.get("linux_count")
                if windows_count is not None or linux_count is not None:
                    bullets.append(
                        f"<li>Windows {self._sanitize_cell(windows_count or 0)} • Linux {self._sanitize_cell(linux_count or 0)}</li>"
                    )
                if os_inventory_meta.get("count") is not None:
                    bullets.append(
                        f"<li>OS inventory records cached: {self._sanitize_cell(os_inventory_meta.get('count', 0))}</li>"
                    )
                versions = os_section.get("top_versions") or []
                section_parts = ["<section><h3>Operating System Coverage</h3>"]
                section_parts.append(f"<ul>{''.join(bullets)}</ul>")
                if versions:
                    version_rows = [
                        [
                            item.get("name_version", "Unknown"),
                            str(item.get("count", 0)),
                        ]
                        for item in versions
                    ]
                    version_footnote = f"Showing top {len(versions)} versions."
                    table = self._render_html_table(
                        ["Version", "Count"],
                        version_rows,
                        footnote=version_footnote,
                        highlight_first_column=True,
                    )
                    if table:
                        section_parts.append(f"<div><h4>Top OS Versions</h4>{table}</div>")
                section_parts.append("</section>")
                sections.append("".join(section_parts))

        if include_os_sections and paginated_rows_meta:
            paginated_rows = paginated_rows_meta.get("rows") if isinstance(paginated_rows_meta.get("rows"), list) else []
            page_size_value = paginated_rows_meta.get("page_size")
            total_pages_value = paginated_rows_meta.get("total_pages")
            page_size = int(page_size_value) if isinstance(page_size_value, int) and page_size_value > 0 else 25
            total_pages = (
                int(total_pages_value)
                if isinstance(total_pages_value, int) and total_pages_value > 0
                else (math.ceil(len(paginated_rows) / page_size) if paginated_rows else 0)
            )

            if paginated_rows:
                section_parts = ["<section><h3>Operating System Inventory</h3>"]
                for index in range(total_pages or 1):
                    start = index * page_size
                    end = min(start + page_size, len(paginated_rows))
                    chunk = paginated_rows[start:end]
                    if not chunk:
                        continue
                    caption = f"OS Inventory (Page {index + 1} of {total_pages or 1})"
                    footnote_parts = [f"Rows {start + 1}-{end} of {len(paginated_rows)}"]
                    if os_inventory_meta.get("count") is not None:
                        footnote_parts.append(
                            f"Original records: {self._sanitize_cell(os_inventory_meta.get('count', 0))}"
                        )
                    if os_inventory_meta.get("from_cache"):
                        footnote_parts.append("Retrieved from cache.")
                    table = self._render_html_table(
                        ["Computer", "OS", "Version", "Type"],
                        chunk,
                        caption=caption,
                        footnote=" • ".join(footnote_parts),
                        highlight_first_column=True,
                    )
                    if table:
                        section_parts.append(table)
                section_parts.append("</section>")
                sections.append("".join(section_parts))
            elif include_os_sections:
                sections.append(
                    "<section><h3>Operating System Inventory</h3><p>No OS inventory records were returned.</p></section>"
                )

        if include_os_sections and os_eol_checks and isinstance(os_eol_checks.get("results"), list):
            eol_results = os_eol_checks.get("results", [])
            if eol_results:
                table_rows = [
                    [
                        item.get("software") or "Unknown",
                        item.get("version") or "-",
                        item.get("eol_date") or "Unknown",
                        item.get("status") or "Unknown",
                        item.get("support_status") or "Unknown",
                        item.get("agent_used") or "orchestrator",
                    ]
                    for item in eol_results
                ]
                footnote_parts = []
                if os_eol_checks.get("total_checked") is not None:
                    footnote_parts.append(f"Checked {os_eol_checks.get('total_checked')} OS variants")
                success_count = sum(1 for item in eol_results if item.get("success"))
                footnote_parts.append(f"EOL matches found: {success_count}")
                failures = os_eol_checks.get("failures") if isinstance(os_eol_checks.get("failures"), list) else []
                if failures:
                    footnote_parts.append(f"Failed lookups: {len(failures)}")
                table = self._render_html_table(
                    ["OS", "Version", "EOL Date", "Status", "Support", "Agent"],
                    table_rows,
                    footnote=" • ".join(footnote_parts) if footnote_parts else None,
                    highlight_first_column=True,
                )
                if table:
                    sections.append(f"<section><h3>Operating System EOL Coverage</h3>{table}</section>")

        target_computer = software_inventory_meta.get("target_computer")
        raw_target_rows = software_inventory_meta.get("target_rows")
        target_rows = [row for row in raw_target_rows if isinstance(row, list)] if isinstance(raw_target_rows, list) else []
        target_results = software_inventory_meta.get("target_results")
        if target_computer and (target_rows or allow_empty_sections or (isinstance(target_results, int) and target_results == 0)):
            section_parts = [f"<section><h3>Installed Software on {self._sanitize_cell(target_computer)}</h3>"]
            if target_rows:
                page_size_value = software_inventory_meta.get("target_page_size")
                page_size = int(page_size_value) if isinstance(page_size_value, int) and page_size_value > 0 else 50
                total_rows = len(target_rows)
                total_pages_value = software_inventory_meta.get("target_total_pages")
                total_pages = int(total_pages_value) if isinstance(total_pages_value, int) and total_pages_value > 0 else max(1, math.ceil(total_rows / page_size) if page_size else 1)

                base_footnotes: List[str] = []
                stored_parts = software_inventory_meta.get("target_footnote_parts")
                if isinstance(stored_parts, list):
                    for part in stored_parts:
                        if part:
                            base_footnotes.append(part)
                if isinstance(target_results, int):
                    entries_text = f"Entries: {target_results}"
                    if entries_text not in base_footnotes:
                        base_footnotes.insert(0, entries_text)
                if software_inventory_meta.get("target_from_cache"):
                    cache_text = "Retrieved from cache."
                    if cache_text not in base_footnotes:
                        base_footnotes.append(cache_text)

                for page_index in range(total_pages):
                    start = page_index * page_size if page_size else 0
                    end = min(start + page_size, total_rows) if page_size else total_rows
                    chunk = target_rows[start:end] if page_size else target_rows
                    if not chunk:
                        continue
                    page_notes = [f"Rows {start + 1}-{end} of {total_rows}"]
                    for part in base_footnotes:
                        if part and part not in page_notes:
                            page_notes.append(part)
                    table = self._render_html_table(
                        ["Software", "Version", "Publisher", "Last Seen"],
                        chunk,
                        caption=f"Software Inventory (Page {page_index + 1} of {total_pages})",
                        footnote=" • ".join(page_notes) if page_notes else None,
                        highlight_first_column=True,
                    )
                    if table:
                        section_parts.append(table)
            else:
                section_parts.append("<p>No software inventory records were found in the last 90 days.</p>")
            section_parts.append("</section>")
            sections.append("".join(section_parts))

        if top_software:
            software_sample_footnote_parts: List[str] = []
            if software_inventory_meta.get("count") is not None:
                software_sample_footnote_parts.append(
                    f"Source rows: {software_inventory_meta.get('count')}"
                )
            software_sample_footnote_parts.append(f"Showing top {len(top_software)} entries.")
            if software_inventory_meta.get("from_cache"):
                software_sample_footnote_parts.append("Retrieved from cache.")
            software_sample_footnote = " • ".join(software_sample_footnote_parts) if software_sample_footnote_parts else None
            table = self._render_html_table(
                ["Software", "Installations", "Computers"],
                top_software,
                footnote=software_sample_footnote,
                highlight_first_column=True,
            )
            if table:
                sections.append(f"<section><h3>Top Installed Software (sample)</h3>{table}</section>")

        if eol_lookup:
            heading = "EOL Lookup"
            subject = eol_lookup.get("software")
            version = eol_lookup.get("version")
            if subject:
                heading += f" — {self._sanitize_cell(subject)}"
                if version:
                    heading += f" {self._sanitize_cell(version)}"
            if eol_lookup.get("success"):
                eol_footnote_parts: List[str] = []
                if eol_lookup.get("confidence") is not None:
                    eol_footnote_parts.append(f"Confidence: {eol_lookup.get('confidence')}")
                if eol_lookup.get("days_until_eol") is not None:
                    eol_footnote_parts.append(f"Days until EOL: {eol_lookup.get('days_until_eol')}")
                eol_footnote = " • ".join(eol_footnote_parts) if eol_footnote_parts else None
                table = self._render_html_table(
                    ["EOL Date", "Status", "Risk", "Support", "Agent"],
                    [[
                        eol_lookup.get("eol_date") or "Unknown",
                        eol_lookup.get("status") or "Unknown",
                        eol_lookup.get("risk_level") or "unknown",
                        eol_lookup.get("support_status") or "Unknown",
                        eol_lookup.get("agent_used") or "orchestrator",
                    ]],
                    footnote=eol_footnote,
                )
                body = table or "<p>EOL data retrieved.</p>"
            else:
                error_text = eol_lookup.get("error") or "No EOL data available"
                body = f"<p>{self._sanitize_cell(error_text)}</p>"
            sections.append(f"<section><h3>{heading}</h3>{body}</section>")

        return "".join(section for section in sections if section).strip()

    def _fallback_response(
        self,
        *,
        user_message: str,
        conversation_id: int,
        started_at: float,
        error: Optional[str],
        agent_metadata: Optional[Dict[str, Any]] = None,
        agents_called: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        total_time = time.time() - started_at
        cache_stats_manager.record_agent_request(
            agent_name=self.agent_name,
            response_time_ms=total_time * 1000,
            was_cache_hit=False,
            had_error=True,
            software_name="inventory_assistant",
            version="preview",
            url="/api/inventory-assistant",
        )

        response_text = (
            "I could not reach the Microsoft Agent Framework inventory assistant service right now. "
            "Please verify your Azure OpenAI configuration and try again."
        )
        if error:
            response_text += f"\n\nDebug detail: {error}"

        self._append_agent_communication(
            role="assistant",
            content=response_text,
            conversation_id=conversation_id,
            metadata={"fallback": True, "error": error},
        )
        return self._build_response_payload(
            user_message=user_message,
            response_text=response_text,
            conversation_id=conversation_id,
            processing_seconds=total_time,
            confirmation_state="error",
            error=error,
            agent_metadata=agent_metadata,
            agents_called=agents_called,
        )

    def _determine_agent_plan(self, intent: Dict[str, Any]) -> List[str]:
        plan: List[str] = []

        wants_inventory = bool(intent.get("is_inventory_query"))
        wants_os_inventory = bool(intent.get("is_os_inventory_query"))
        wants_software_inventory = bool(intent.get("is_software_inventory_query"))
        software_only_request = (
            (wants_inventory or wants_software_inventory)
            and wants_software_inventory
            and not wants_os_inventory
        )

        if wants_inventory or wants_software_inventory:
            plan.extend(["inventory_summary", "software_inventory_sample"])

            if not software_only_request:
                plan.extend(["os_summary", "os_inventory_sample", "os_inventory_eol_checks"])
        elif wants_os_inventory:
            plan.extend(["os_summary", "os_inventory_sample", "os_inventory_eol_checks"])

        if intent.get("is_eol_query") or intent.get("is_approaching_eol_query"):
            plan.append("eol_lookup")

        # Preserve order while removing duplicates
        seen = set()
        ordered_plan: List[str] = []
        for step in plan:
            if step in seen:
                continue
            ordered_plan.append(step)
            seen.add(step)
        return ordered_plan

    async def _execute_inventory_summary(
        self,
        orchestrator: Any,
        *,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
    ) -> None:
        inventory_agent = orchestrator.agents.get("inventory")
        if not inventory_agent or not hasattr(inventory_agent, "get_inventory_summary"):
            return

        try:
            summary = await asyncio.wait_for(
                inventory_agent.get_inventory_summary(),
                timeout=20.0,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Inventory summary retrieval failed: %s", exc)
            return

        metadata["inventory_summary"] = self._shrink_inventory_summary(summary)
        agents_called.append("inventory")
        inventory_section = self._format_inventory_insights(summary)
        if inventory_section:
            insights_sections.append(inventory_section)

        summary_meta = metadata.get("inventory_summary", {}).get("software", {})
        self._append_agent_communication(
            role="tool",
            content="Inventory summary retrieved for conversational grounding.",
            conversation_id=conversation_id,
            metadata={
                "agent": "inventory",
                "type": "summary",
                "total_software": summary_meta.get("total_software"),
                "total_computers": summary_meta.get("total_computers"),
            },
            agent_name="inventory",
        )

    async def _execute_software_inventory_sample(
        self,
        orchestrator: Any,
        *,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
        target_computer: Optional[str] = None,
    ) -> None:
        software_agent = orchestrator.agents.get("software_inventory")
        if not software_agent or not hasattr(software_agent, "get_software_inventory"):
            return

        request_kwargs: Dict[str, Any] = {"limit": 500, "use_cache": True}
        if target_computer:
            request_kwargs.update({"computer_filter": target_computer, "limit": 1000})

        try:
            software_result = await asyncio.wait_for(
                software_agent.get_software_inventory(**request_kwargs),
                timeout=25.0,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Software inventory sample unavailable: %s", exc)
            agents_called.append("software_inventory")
            self._append_agent_communication(
                role="tool",
                content="Software inventory sample request failed.",
                conversation_id=conversation_id,
                metadata={
                    "agent": "software_inventory",
                    "type": "sample",
                    "success": False,
                    "error": str(exc),
                    "target_computer": target_computer,
                },
                agent_name="software_inventory",
            )
            return

        success = bool(software_result.get("success"))
        rows_payload = software_result.get("data") if isinstance(software_result, dict) else []
        rows_data = rows_payload if isinstance(rows_payload, list) else []
        total_items = len(rows_data)
        from_cache = bool(software_result.get("from_cache")) if isinstance(software_result, dict) else False

        software_meta = metadata.setdefault("software_inventory", {})
        software_meta.update(
            {
                "success": success,
                "count": total_items,
                "from_cache": from_cache,
                "error": software_result.get("error") if not success else None,
            }
        )

        agents_called.append("software_inventory")

        communication_metadata: Dict[str, Any] = {
            "agent": "software_inventory",
            "type": "sample",
            "success": success,
            "total_items": total_items,
            "from_cache": from_cache,
        }

        if target_computer:
            normalized_target = target_computer.lower()
            matched_rows = [
                row
                for row in rows_data
                if isinstance(row, dict) and (row.get("computer") or "").lower() == normalized_target
            ]
            if not matched_rows and rows_data:
                matched_rows = rows_data

            display_host = matched_rows[0].get("computer") if matched_rows else target_computer
            software_meta.update(
                {
                    "target_computer": display_host,
                    "target_results": len(matched_rows),
                    "target_from_cache": from_cache,
                }
            )

            row_values: List[List[str]] = []
            for item in matched_rows:
                row = [
                    item.get("name") or "Unknown",
                    item.get("version") or "-",
                    item.get("publisher") or "Unknown",
                    self._format_last_seen(item.get("last_seen")),
                ]
                row_values.append(row)

            if row_values:
                base_footnotes: List[str] = [
                    f"Entries: {len(row_values)}",
                    "Source: Log Analytics ConfigurationData",
                ]
                if from_cache:
                    base_footnotes.append("Retrieved from cache.")

                page_size = 50
                total_pages = max(1, math.ceil(len(row_values) / page_size))

                software_meta["target_rows"] = row_values
                software_meta["target_footnote_parts"] = list(base_footnotes)
                software_meta["target_page_size"] = page_size
                software_meta["target_total_pages"] = total_pages

                section_parts: List[str] = [
                    f"<section><h3>Installed Software on {self._sanitize_cell(display_host)}</h3>"
                ]
                for page_index in range(total_pages):
                    start = page_index * page_size
                    end = min(start + page_size, len(row_values))
                    chunk = row_values[start:end]
                    if not chunk:
                        continue
                    page_footnotes = [
                        f"Rows {start + 1}-{end} of {len(row_values)}",
                        *base_footnotes,
                    ]
                    unique_footnotes: List[str] = []
                    for note in page_footnotes:
                        if note and note not in unique_footnotes:
                            unique_footnotes.append(note)
                    table = self._render_html_table(
                        ["Software", "Version", "Publisher", "Last Seen"],
                        chunk,
                        caption=f"Software Inventory (Page {page_index + 1} of {total_pages})",
                        footnote=" • ".join(unique_footnotes),
                        highlight_first_column=True,
                    )
                    if table:
                        section_parts.append(table)
                section_parts.append("</section>")
                insights_sections.append("".join(section_parts))
            else:
                heading = f"Installed Software on {self._sanitize_cell(target_computer)}"
                insights_sections.append(
                    f"<section><h3>{heading}</h3><p>No software inventory records were found in the last 90 days.</p></section>"
                )
                software_meta["target_rows"] = []
                software_meta["target_footnote_parts"] = []
                software_meta["target_page_size"] = 0
                software_meta["target_total_pages"] = 0

            page_size_metric = software_meta.get("target_page_size")
            if isinstance(page_size_metric, int) and page_size_metric > 0:
                displayed_rows = min(len(row_values), page_size_metric)
            else:
                displayed_rows = len(row_values)

            communication_metadata.update(
                {
                    "target_computer": display_host,
                    "target_results": len(matched_rows),
                    "displayed_rows": displayed_rows,
                    "pages": software_meta.get("target_total_pages", 0),
                }
            )
            tool_message = (
                f"Software inventory retrieved for {display_host}."
                if success and matched_rows
                else f"No inventory entries found for {target_computer}."
            )
        else:
            top_rows = self._summarize_top_software(rows_data, limit=15)
            if top_rows:
                software_meta["top_software"] = top_rows
                sample_footnote_parts: List[str] = [f"Source rows: {total_items}", f"Showing top {len(top_rows)} entries."]
                if from_cache:
                    sample_footnote_parts.append("Retrieved from cache.")
                table = self._render_html_table(
                    ["Software", "Installations", "Computers"],
                    top_rows,
                    footnote=" • ".join(sample_footnote_parts),
                    highlight_first_column=True,
                )
                if table:
                    insights_sections.append(f"<section><h3>Top Installed Software (sample)</h3>{table}</section>")
                communication_metadata["rows"] = len(top_rows)
            tool_message = (
                "Software inventory sample aggregated for chat."
                if success and top_rows
                else "Software inventory request completed."
            )

        self._append_agent_communication(
            role="tool",
            content=tool_message,
            conversation_id=conversation_id,
            metadata=communication_metadata,
            agent_name="software_inventory",
        )

    async def _execute_os_summary(
        self,
        orchestrator: Any,
        *,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
    ) -> None:
        os_agent = orchestrator.agents.get("os_inventory")
        if not os_agent or not hasattr(os_agent, "get_os_summary"):
            return

        try:
            os_summary = await asyncio.wait_for(os_agent.get_os_summary(), timeout=20.0)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("OS summary retrieval failed: %s", exc)
            return

        metadata["os_summary"] = {
            "total_computers": os_summary.get("total_computers"),
            "windows_count": os_summary.get("windows_count"),
            "linux_count": os_summary.get("linux_count"),
            "top_versions": os_summary.get("top_versions", [])[:5],
        }
        agents_called.append("os_inventory")
        os_section = self._format_os_insights(os_summary)
        if os_section:
            insights_sections.append(os_section)

        self._append_agent_communication(
            role="tool",
            content="OS inventory summary retrieved for chat.",
            conversation_id=conversation_id,
            metadata={
                "agent": "os_inventory",
                "type": "summary",
                "total_computers": os_summary.get("total_computers"),
            },
            agent_name="os_inventory",
        )

    async def _execute_os_inventory_sample(
        self,
        orchestrator: Any,
        *,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
    ) -> None:
        os_agent = orchestrator.agents.get("os_inventory")
        if not os_agent or not hasattr(os_agent, "get_os_inventory"):
            return

        try:
            os_inventory_result = await asyncio.wait_for(
                os_agent.get_os_inventory(limit=None, use_cache=True),
                timeout=25.0,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("OS inventory sample unavailable: %s", exc)
            agents_called.append("os_inventory")
            self._append_agent_communication(
                role="tool",
                content="OS inventory sample request failed.",
                conversation_id=conversation_id,
                metadata={
                    "agent": "os_inventory",
                    "type": "sample",
                    "success": False,
                    "error": str(exc),
                },
                agent_name="os_inventory",
            )
            return

        agents_called.append("os_inventory")
        os_data_list = (
            os_inventory_result.get("data")
            if isinstance(os_inventory_result, dict) and isinstance(os_inventory_result.get("data"), list)
            else []
        )
        all_rows = self._summarize_os_inventory(os_data_list, limit=None)
        from_cache = bool(os_inventory_result.get("from_cache")) if isinstance(os_inventory_result, dict) else False

        full_records: List[Dict[str, Optional[str]]] = []
        for item in os_data_list:
            os_name_value = (
                item.get("os_name")
                or item.get("name")
                or item.get("display_name")
                or item.get("operating_system")
            )
            os_name = str(os_name_value).strip() if os_name_value is not None else ""
            if not os_name or os_name.lower() == "unknown":
                continue

            version_value = item.get("os_version") or item.get("version") or item.get("build")
            version = str(version_value).strip() if version_value is not None else None
            if version == "":
                version = None

            computer_value = item.get("computer") or item.get("computer_name") or item.get("machine_name")
            computer = str(computer_value).strip() if computer_value is not None else None
            if computer == "":
                computer = None

            full_records.append(
                {
                    "os_name": os_name,
                    "version": version,
                    "computer": computer,
                }
            )

        metadata.setdefault("os_inventory", {})
        metadata["os_inventory"].update(
            {
                "count": len(os_data_list),
                "success": bool(os_inventory_result.get("success", True)) if isinstance(os_inventory_result, dict) else bool(all_rows),
                "from_cache": from_cache,
                "sample": all_rows[:15] if all_rows else metadata.get("os_inventory", {}).get("sample"),
                "paginated_rows": {
                    "rows": all_rows,
                    "page_size": 25 if all_rows else 0,
                    "total_pages": math.ceil(len(all_rows) / 25) if all_rows else 0,
                },
                "full_records": full_records,
            }
        )

        if all_rows:
            page_size = 25
            total_pages = math.ceil(len(all_rows) / page_size)
            section_parts: List[str] = ["<section><h3>Operating System Inventory</h3>"]
            for index in range(total_pages):
                start = index * page_size
                end = min(start + page_size, len(all_rows))
                chunk = all_rows[start:end]
                if not chunk:
                    continue
                caption = f"OS Inventory (Page {index + 1} of {total_pages})"
                footnote_parts = [f"Rows {start + 1}-{end} of {len(all_rows)}"]
                if len(all_rows) != len(os_data_list):
                    footnote_parts.append(f"Original records: {len(os_data_list)}")
                if from_cache:
                    footnote_parts.append("Retrieved from cache.")
                table = self._render_html_table(
                    ["Computer", "OS", "Version", "Type"],
                    chunk,
                    caption=caption,
                    footnote=" • ".join(footnote_parts),
                    highlight_first_column=True,
                )
                if table:
                    section_parts.append(table)
            section_parts.append("</section>")
            section_html = "".join(section_parts)
            if section_html:
                insights_sections.append(section_html)
        else:
            insights_sections.append(
                "<section><h3>Operating System Inventory</h3><p>No OS inventory records were returned.</p></section>"
            )

        self._append_agent_communication(
            role="tool",
            content="OS inventory data retrieved for chat." if all_rows else "OS inventory request completed.",
            conversation_id=conversation_id,
            metadata={
                "agent": "os_inventory",
                "type": "sample",
                "success": bool(all_rows) or bool(metadata.get("os_inventory", {}).get("success")),
                "rows": len(all_rows),
                "total_items": len(os_data_list),
                "from_cache": from_cache,
                "pages": math.ceil(len(all_rows) / 25) if all_rows else 0,
            },
            agent_name="os_inventory",
        )

    async def _execute_os_inventory_eol_checks(
        self,
        orchestrator: Any,
        *,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
    ) -> None:
        os_meta = metadata.get("os_inventory") if isinstance(metadata, dict) else None
        if not isinstance(os_meta, dict):
            return

        full_records = os_meta.get("full_records") if isinstance(os_meta.get("full_records"), list) else []
        if not full_records:
            return

        unique_targets: List[Dict[str, Optional[str]]] = []
        seen: Set[Tuple[str, str]] = set()
        for record in full_records:
            if not isinstance(record, dict):
                continue
            os_name_value = record.get("os_name")
            version_value = record.get("version")
            os_name = str(os_name_value).strip() if os_name_value is not None else ""
            if not os_name:
                continue
            version_clean = str(version_value).strip() if version_value is not None else ""
            version = version_clean or None
            key = (os_name.lower(), (version or "").lower())
            if key in seen:
                continue
            seen.add(key)
            unique_targets.append({"software": os_name, "version": version})

        if not unique_targets:
            return

        eol_results: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        total_checked = len(unique_targets)

        for target in unique_targets:
            software = (target.get("software") or "").strip()
            version = target.get("version")
            try:
                eol_response = await asyncio.wait_for(
                    orchestrator.get_autonomous_eol_data(software, version),
                    timeout=25.0,
                )
            except Exception as exc:  # pylint: disable=broad-except
                failures.append(
                    {
                        "software": software,
                        "version": version,
                        "error": str(exc),
                    }
                )
                logger.debug("OS EOL lookup failed for %s %s: %s", software, version or "", exc)
                continue

            shrinked = self._shrink_eol_result(software, version, eol_response)
            eol_results.append(shrinked)
            agent_used = shrinked.get("agent_used")
            if agent_used:
                agents_called.append(agent_used)

        success_count = sum(1 for item in eol_results if item.get("success"))
        os_meta["eol_checks"] = {
            "total_checked": total_checked,
            "results": eol_results,
            "failures": failures,
        }

        insights_section_added = False
        if eol_results:
            table_rows = [
                [
                    result.get("software") or "Unknown",
                    result.get("version") or "-",
                    result.get("eol_date") or "Unknown",
                    result.get("status") or "Unknown",
                    result.get("support_status") or "Unknown",
                    result.get("agent_used") or "orchestrator",
                ]
                for result in eol_results
            ]
            footnote_parts = [f"Checked {total_checked} OS variants", f"EOL matches found: {success_count}"]
            if failures:
                footnote_parts.append(f"Failed lookups: {len(failures)}")
            table = self._render_html_table(
                ["OS", "Version", "EOL Date", "Status", "Support", "Agent"],
                table_rows,
                footnote=" • ".join(footnote_parts),
                highlight_first_column=True,
            )
            if table:
                insights_sections.append(f"<section><h3>Operating System EOL Coverage</h3>{table}</section>")
                insights_section_added = True

        if not insights_section_added and failures:
            error_messages = [
                f"{failure.get('software', 'Unknown')} {failure.get('version') or ''} ({failure.get('error', 'error')})"
                for failure in failures
            ]
            insights_sections.append(
                "<section><h3>Operating System EOL Coverage</h3>"
                f"<p>{self._sanitize_cell('Failed lookups: ' + '; '.join(error_messages))}</p></section>"
            )

        agents_called.append("eol_orchestrator")
        self._append_agent_communication(
            role="tool",
            content=(
                "EOL coverage evaluated for operating systems."
                if eol_results
                else "EOL coverage check attempted for operating systems."
            ),
            conversation_id=conversation_id,
            metadata={
                "agent": "eol_orchestrator",
                "type": "os_inventory_eol",
                "checked": total_checked,
                "successes": success_count,
                "failures": len(failures),
            },
            agent_name="eol_orchestrator",
        )

    async def _execute_eol_lookup(
        self,
        orchestrator: Any,
        *,
        user_message: str,
        metadata: Dict[str, Any],
        insights_sections: List[str],
        agents_called: List[str],
        conversation_id: int,
    ) -> None:
        software_name, version = self._extract_target_software(user_message)
        if not software_name:
            return

        try:
            eol_result = await asyncio.wait_for(
                orchestrator.get_autonomous_eol_data(software_name, version),
                timeout=35.0,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("EOL lookup failed: %s", exc)
            metadata["eol_lookup_error"] = str(exc)
            return

        eol_payload = self._shrink_eol_result(software_name, version, eol_result)
        metadata["eol_lookup"] = eol_payload
        agent_used = eol_payload.get("agent_used") or "eol_orchestrator"
        agents_called.append(agent_used)

        eol_section = self._format_eol_insights(eol_payload)
        if eol_section:
            insights_sections.append(eol_section)

        self._append_agent_communication(
            role="tool",
            content=f"EOL lookup completed for {software_name}{f' {version}' if version else ''}.",
            conversation_id=conversation_id,
            metadata={
                "agent": agent_used,
                "type": "eol_lookup",
                "success": eol_payload.get("success", False),
                "eol_date": eol_payload.get("eol_date"),
                "error": eol_payload.get("error"),
            },
            agent_name=agent_used,
        )

    def _build_declined_confirmation_response(
        self,
        *,
        user_message: str,
        original_message: Optional[str],
        conversation_id: int,
        started_at: float,
    ) -> Dict[str, Any]:
        self._append_agent_communication(
            role="assistant",
            content=self._DECLINED_CONFIRMATION_MESSAGE,
            conversation_id=conversation_id,
            metadata={"confirmation_state": "declined", "original_message": original_message},
        )
        return self._build_response_payload(
            user_message=user_message,
            response_text=self._DECLINED_CONFIRMATION_MESSAGE,
            conversation_id=conversation_id,
            processing_seconds=time.time() - started_at,
            confirmation_state="declined",
            error=None,
        )

    def _build_response_payload(
        self,
        *,
        user_message: str,
        response_text: str,
        conversation_id: int,
        processing_seconds: float,
        confirmation_state: str,
        error: Optional[str],
        agent_metadata: Optional[Dict[str, Any]] = None,
        agents_called: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        conversation_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "conversation_id": conversation_id,
            "user_message": user_message,
            "response": response_text,
            "processing_time": processing_seconds,
            "confirmation_state": confirmation_state,
            "error": error,
            "agent_metadata": agent_metadata,
        }
        self.conversation_history.append(conversation_entry)

        agents_involved = ["AgentFrameworkChatAgent"]
        if agents_called:
            for agent in agents_called:
                if agent and agent not in agents_involved:
                    agents_involved.append(agent)

        metadata_payload: Dict[str, Any] = {
            "orchestrator": "agent_framework",
            "confirmation_state": confirmation_state,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if agent_metadata:
            metadata_payload["agent_context"] = agent_metadata

        if agents_called:
            metadata_payload["agents_called"] = [
                agent for agent in agents_called if agent
            ]

        return {
            "response": response_text,
            "conversation_messages": [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response_text},
            ],
            "agent_communications": self.agent_interaction_logs[-25:],
            "agents_involved": agents_involved,
            "total_exchanges": len(self.conversation_history),
            "session_id": self.session_id,
            "processing_time": processing_seconds,
            "system": "microsoft_agent_framework",
            "conversation_id": conversation_id,
            "confirmation_required": False,
            "confirmation_declined": confirmation_state == "declined",
            "pending_message": None,
            "fast_path": False,
            "error": error,
            "metadata": metadata_payload,
        }

    async def _gather_agent_grounding(
        self,
        *,
        user_message: str,
        conversation_id: int,
    ) -> Dict[str, Any]:
        insights_sections: List[str] = []
        metadata: Dict[str, Any] = {}
        agents_called: List[str] = []

        try:
            intent = QueryPatterns.analyze_query_intent(user_message)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Query intent analysis failed: %s", exc)
            return {"insights": "", "metadata": {}, "agents_called": []}

        if not any(
            intent.get(flag)
            for flag in ("is_inventory_query", "is_os_inventory_query", "is_eol_query", "is_approaching_eol_query")
        ):
            return {"insights": "", "metadata": {}, "agents_called": []}

        try:
            from main import get_eol_orchestrator  # Local import to avoid circular dependency
        except ImportError as exc:
            logger.debug("Unable to import get_eol_orchestrator: %s", exc)
            return {"insights": "", "metadata": {}, "agents_called": []}

        orchestrator = get_eol_orchestrator()
        if not orchestrator or not getattr(orchestrator, "agents", None):
            return {"insights": "", "metadata": {}, "agents_called": []}

        plan = self._determine_agent_plan(intent)
        if not plan:
            return {"insights": "", "metadata": {}, "agents_called": []}

        metadata["requested_intents"] = intent
        metadata["requested_plan"] = list(plan)
        metadata["include_os_sections"] = any(
            step in {"os_summary", "os_inventory_sample", "os_inventory_eol_checks"}
            for step in plan
        )

        target_computer = self._extract_target_computer(user_message)
        if target_computer:
            metadata["target_computer"] = target_computer

        async def run_step(step_name: str):
            if step_name == "inventory_summary":
                await self._execute_inventory_summary(
                    orchestrator,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                )
            elif step_name == "software_inventory_sample":
                await self._execute_software_inventory_sample(
                    orchestrator,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                    target_computer=target_computer,
                )
            elif step_name == "os_summary":
                await self._execute_os_summary(
                    orchestrator,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                )
            elif step_name == "os_inventory_sample":
                await self._execute_os_inventory_sample(
                    orchestrator,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                )
            elif step_name == "os_inventory_eol_checks":
                await self._execute_os_inventory_eol_checks(
                    orchestrator,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                )
            elif step_name == "eol_lookup":
                await self._execute_eol_lookup(
                    orchestrator,
                    user_message=user_message,
                    metadata=metadata,
                    insights_sections=insights_sections,
                    agents_called=agents_called,
                    conversation_id=conversation_id,
                )

        # Run plan steps concurrently to reduce end-to-end latency
        step_tasks = [asyncio.create_task(run_step(step)) for step in plan]
        if step_tasks:
            await asyncio.gather(*step_tasks, return_exceptions=True)

        unique_agents: List[str] = []
        for agent in agents_called:
            if agent and agent not in unique_agents:
                unique_agents.append(agent)

        insights_text = "\n".join(section for section in insights_sections if section)
        return {
            "insights": insights_text,
            "metadata": metadata,
            "agents_called": unique_agents,
        }

    def _extract_response_text(self, response: Optional[ChatResponse]) -> str:
        """Normalize Agent Framework responses into a text payload."""

        if response is None:
            return ""

        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        messages = getattr(response, "messages", None)
        if isinstance(messages, list):
            for message in reversed(messages):
                role = getattr(message, "role", None)
                if role not in {"assistant", "system"}:
                    continue

                text = getattr(message, "text", None)
                if isinstance(text, str) and text.strip():
                    return text.strip()

                contents = getattr(message, "contents", None)
                if not isinstance(contents, (list, tuple)):
                    continue

                fragments: List[str] = []
                for item in contents:
                    item_text = None
                    if hasattr(item, "text"):
                        item_text = getattr(item, "text", None)
                    elif isinstance(item, dict):
                        item_text = item.get("text") or item.get("content")

                    if isinstance(item_text, str) and item_text.strip():
                        fragments.append(item_text.strip())

                if fragments:
                    return "\n".join(fragments).strip()

        return ""

    def _format_inventory_insights(self, summary: Optional[Dict[str, Any]]) -> str:
        if not isinstance(summary, dict):
            return ""

        software_summary = summary.get("software_inventory", {}) if summary else {}
        os_summary = summary.get("os_inventory", {}) if summary else {}
        bullets: List[str] = []

        if isinstance(software_summary, dict) and software_summary.get("success"):
            bullets.append(
                f"<li>Software items tracked: {self._sanitize_cell(software_summary.get('total_software', 0))}"
                f" across {self._sanitize_cell(software_summary.get('total_computers', 0))} computers</li>"
            )
            bullets.append(
                f"<li>Software cache source: {'Yes' if software_summary.get('from_cache') else 'No'}</li>"
            )
        elif isinstance(software_summary, dict) and software_summary.get("error"):
            bullets.append(f"<li>Software summary unavailable: {self._sanitize_cell(software_summary.get('error'))}</li>")

        if isinstance(os_summary, dict) and (os_summary.get("success") or os_summary):
            total_computers = os_summary.get("total_computers")
            windows_count = os_summary.get("windows_count")
            linux_count = os_summary.get("linux_count")
            if total_computers is not None:
                bullets.append(
                    f"<li>OS coverage: {self._sanitize_cell(total_computers)} computers (Windows {self._sanitize_cell(windows_count or 0)}"
                    f" • Linux {self._sanitize_cell(linux_count or 0)})</li>"
                )

        sections: List[str] = ["<section><h3>Inventory Snapshot (last 90 days)</h3>"]
        if bullets:
            sections.append(f"<ul>{''.join(bullets)}</ul>")

        top_publishers = software_summary.get("top_publishers", [])[:5] if isinstance(software_summary, dict) else []
        if top_publishers:
            publisher_rows = [
                [
                    item.get("publisher", "Unknown"),
                    str(item.get("installations", 0)),
                ]
                for item in top_publishers
            ]
            publisher_footnote = f"Showing top {len(top_publishers)} publishers."
            table = self._render_html_table(
                ["Publisher", "Installations"],
                publisher_rows,
                footnote=publisher_footnote,
                highlight_first_column=True,
            )
            if table:
                sections.append(f"<div><h4>Top Publishers</h4>{table}</div>")

        top_categories = software_summary.get("top_categories", [])[:5] if isinstance(software_summary, dict) else []
        if top_categories:
            category_rows = [
                [
                    item.get("category", "Unknown"),
                    str(item.get("installations", 0)),
                ]
                for item in top_categories
            ]
            category_footnote = f"Showing top {len(top_categories)} categories."
            table = self._render_html_table(
                ["Category", "Installations"],
                category_rows,
                footnote=category_footnote,
                highlight_first_column=True,
            )
            if table:
                sections.append(f"<div><h4>Top Categories</h4>{table}</div>")

        sections.append("</section>")
        return "".join(sections)

    def _format_os_insights(self, os_summary: Optional[Dict[str, Any]]) -> str:
        if not isinstance(os_summary, dict):
            return ""

        bullets: List[str] = []
        total_computers = os_summary.get("total_computers")
        if total_computers is not None:
            bullets.append(f"<li>Computers reporting: {self._sanitize_cell(total_computers)}</li>")

        windows_count = os_summary.get("windows_count")
        linux_count = os_summary.get("linux_count")
        if windows_count is not None or linux_count is not None:
            bullets.append(
                f"<li>Windows {self._sanitize_cell(windows_count or 0)} • Linux {self._sanitize_cell(linux_count or 0)}</li>"
            )

        sections: List[str] = ["<section><h3>Operating System Coverage</h3>"]
        if bullets:
            sections.append(f"<ul>{''.join(bullets)}</ul>")

        top_versions = os_summary.get("top_versions", [])[:5]
        if top_versions:
            version_rows = [
                [
                    item.get("name_version", "Unknown"),
                    str(item.get("count", 0)),
                ]
                for item in top_versions
            ]
            version_footnote = f"Showing top {len(top_versions)} versions."
            table = self._render_html_table(
                ["Version", "Count"],
                version_rows,
                footnote=version_footnote,
                highlight_first_column=True,
            )
            if table:
                sections.append(f"<div><h4>Top OS Versions</h4>{table}</div>")

        sections.append("</section>")
        return "".join(sections)

    def _format_eol_insights(self, payload: Dict[str, Any]) -> str:
        if not payload:
            return ""

        software_name = payload.get("software") or "Requested software"
        version = payload.get("version")
        heading = f"EOL Intelligence for {self._sanitize_cell(software_name)}"
        if version:
            heading += f" {self._sanitize_cell(version)}"

        if not payload.get("success"):
            error_msg = payload.get("error") or "No EOL data found"
            return f"<section><h3>{heading}</h3><p>{self._sanitize_cell(error_msg)}</p></section>"

        footnote_parts: List[str] = []
        if payload.get("confidence") is not None:
            footnote_parts.append(f"Confidence: {payload.get('confidence')}")
        if payload.get("days_until_eol") is not None:
            footnote_parts.append(f"Days until EOL: {payload.get('days_until_eol')}")
        table = self._render_html_table(
            ["EOL Date", "Status", "Risk", "Support", "Agent"],
            [[
                payload.get("eol_date") or "Unknown",
                payload.get("status") or "Unknown",
                str(payload.get("risk_level") or "unknown"),
                payload.get("support_status") or "Unknown",
                payload.get("agent_used") or "orchestrator",
            ]],
            footnote=" • ".join(footnote_parts) if footnote_parts else None,
        )
        body = table or "<p>EOL data retrieved.</p>"
        return f"<section><h3>{heading}</h3>{body}</section>"

    def _render_html_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        *,
        caption: Optional[str] = None,
        footnote: Optional[str] = None,
        highlight_first_column: bool = False,
    ) -> str:
        if not headers or not rows:
            return ""

        sanitized_headers = [self._sanitize_cell(col) for col in headers]
        normalized_rows: List[List[str]] = []
        for row in rows:
            if not any(str(cell).strip() for cell in row):
                continue
            normalized_rows.append([self._sanitize_cell(cell) for cell in row])

        if not normalized_rows:
            return ""

        table_parts: List[str] = ["<table class=\"mcp-table\" role=\"table\">"]
        if caption:
            table_parts.append(f"<caption>{self._sanitize_cell(caption)}</caption>")

        header_cells = "".join(
            f"<th scope=\"col\">{col or '&#160;'}</th>" for col in sanitized_headers
        )
        table_parts.append(f"<thead><tr>{header_cells}</tr></thead>")

        body_rows: List[str] = []
        for row in normalized_rows:
            cells: List[str] = []
            for idx, cell in enumerate(row):
                rendered = cell or "&#160;"
                if highlight_first_column and idx == 0:
                    cells.append(f"<th scope=\"row\">{rendered}</th>")
                else:
                    cells.append(f"<td>{rendered}</td>")
            body_rows.append(f"<tr>{''.join(cells)}</tr>")

        table_parts.append(f"<tbody>{''.join(body_rows)}</tbody></table>")

        if footnote:
            table_parts.append(f"<div class=\"mcp-meta\">{self._sanitize_cell(footnote)}</div>")

        return "".join(table_parts)

    def _sanitize_cell(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).replace("\n", " ").strip()
        return html.escape(text)

    def _format_last_seen(self, last_seen: Optional[str]) -> str:
        if not last_seen:
            return "Unknown"
        try:
            parsed = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc)
                return parsed.strftime("%Y-%m-%d %H:%M UTC")
            return parsed.strftime("%Y-%m-%d %H:%M")
        except Exception:  # pylint: disable=broad-except
            return str(last_seen)

    def _summarize_top_software(self, records: List[Dict[str, Any]], limit: int = 5) -> List[List[str]]:
        if not records:
            return []

        aggregates: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for item in records:
            name = item.get("name") or item.get("software_name") or item.get("SoftwareName")
            if not name:
                continue
            version = item.get("version") or item.get("software_version") or item.get("CurrentVersion") or ""
            key = (name.strip(), version.strip())
            aggregate = aggregates.setdefault(
                key,
                {
                    "count": 0,
                    "computers": set(),
                },
            )
            count_increment = item.get("computer_count")
            if not isinstance(count_increment, int) or count_increment < 1:
                count_increment = 1
            aggregate["count"] += count_increment
            computer_name = item.get("computer") or item.get("Computer")
            if computer_name:
                aggregate["computers"].add(computer_name)

        sorted_items = sorted(aggregates.items(), key=lambda kv: kv[1]["count"], reverse=True)[:limit]
        rows: List[List[str]] = []
        for (name, version), data in sorted_items:
            display_name = name if not version else f"{name} {version}"
            rows.append([
                self._sanitize_cell(display_name),
                str(data["count"]),
                str(len(data["computers"])) if data["computers"] else "-",
            ])
        return rows

    def _summarize_os_inventory(self, records: List[Dict[str, Any]], limit: Optional[int] = 15) -> List[List[str]]:
        if not records:
            return []

        rows: List[List[str]] = []
        iterable = records if limit is None else records[:limit]
        for item in iterable:
            computer = item.get("computer") or item.get("computer_name") or "Unknown"
            os_name = item.get("os_name") or item.get("name") or "Unknown"
            version = item.get("os_version") or item.get("version") or "Unknown"
            computer_type = item.get("computer_type") or item.get("computerEnvironment") or item.get("computer_environment") or "Unknown"
            rows.append(
                [
                    self._sanitize_cell(computer),
                    self._sanitize_cell(os_name),
                    self._sanitize_cell(version),
                    self._sanitize_cell(computer_type),
                ]
            )

        return rows

    def _shrink_inventory_summary(self, summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(summary, dict):
            return {}

        software = summary.get("software_inventory", {}) if summary else {}
        os_summary = summary.get("os_inventory", {}) if summary else {}

        return {
            "software": {
                "success": software.get("success"),
                "total_software": software.get("total_software"),
                "total_computers": software.get("total_computers"),
                "top_publishers": software.get("top_publishers", [])[:5],
                "top_categories": software.get("top_categories", [])[:5],
            },
            "os": {
                "total_computers": os_summary.get("total_computers"),
                "windows_count": os_summary.get("windows_count"),
                "linux_count": os_summary.get("linux_count"),
                "top_versions": os_summary.get("top_versions", [])[:5],
            },
            "last_updated": summary.get("last_updated"),
        }

    def _shrink_eol_result(
        self,
        software_name: str,
        version: Optional[str],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = {
            "software": software_name,
            "version": version,
            "success": bool(result.get("success")),
            "agent_used": result.get("agent_used"),
            "confidence": result.get("confidence"),
            "error": result.get("error"),
        }

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        base.update(
            {
                "eol_date": data.get("eol_date") or result.get("eol_date"),
                "status": data.get("status") or result.get("status"),
                "support_status": data.get("support_status"),
                "risk_level": data.get("risk_level"),
                "days_until_eol": data.get("days_until_eol"),
            }
        )
        return base

    def _extract_target_computer(self, query: str) -> Optional[str]:
        if not query:
            return None

        lowered = query.lower()
        if not any(token in lowered for token in ("software", "application")):
            return None

        patterns = [
            r"software\s+(?:inventory|installed|list)[^\n]*? on (?:the\s+)?(?P<name>[A-Za-z0-9_.-]+)",
            r"installed on (?:the\s+)?(?P<name>[A-Za-z0-9_.-]+)(?:\s+(?:server|vm|machine))?",
            r"on (?:the\s+)?(?P<name>[A-Za-z0-9_.-]+)\s+(?:server|vm|machine)",
            r"(?:server|vm|machine)\s+(?:named\s+)?(?P<name>[A-Za-z0-9_.-]+)",
        ]

        invalid_tokens = {"server", "software", "inventory", "machine", "vm"}

        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if not match:
                continue
            name = match.group("name").strip(" .,'\"") if match.groupdict().get("name") else None
            if not name or name.lower() in invalid_tokens or len(name) < 2:
                continue
            return name

        return None

    def _extract_target_software(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        if not query:
            return None, None

        cleaned = query.strip()
        cleaned = re.sub(r"[?!,.;]+$", "", cleaned)
        lowered = cleaned.lower()

        candidate = cleaned
        for delimiter in (" for ", " about ", " on ", " regarding ", " of "):
            if delimiter in lowered:
                candidate = cleaned[lowered.index(delimiter) + len(delimiter) :]
                break

        candidate = re.sub(
            r"^(what|when|is|are|does|do|tell me|show me|please|can you|find|give me|list|provide)\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s+(in|within|across)\s+.+$", "", candidate, flags=re.IGNORECASE)
        candidate = candidate.strip(" ")

        if not candidate or not re.search(r"[a-zA-Z]", candidate):
            return None, None

        pattern = re.compile("|".join(re.escape(term) for term in QueryPatterns.EOL_PATTERNS), re.IGNORECASE)
        candidate = pattern.sub("", candidate).strip()

        if not candidate:
            return None, None

        lowered_candidate = candidate.lower()
        inventory_guard_terms = {"inventory", "environment", "fleet", "estate"}
        product_hint_pattern = re.compile(
            r"\b(windows|server|ubuntu|linux|centos|rhel|red hat|debian|suse|sql|oracle|vmware|exchange|office|adobe|sap|java|python|node|chrome|edge|firefox|microsoft 365)\b",
            re.IGNORECASE,
        )
        if any(term in lowered_candidate for term in inventory_guard_terms) and not product_hint_pattern.search(candidate):
            return None, None

        name, version = extract_software_name_and_version(candidate)
        if name:
            name = name.strip(" ,")
        if version:
            version = version.strip()

        if not name or not re.search(r"[a-zA-Z]", name):
            return None, version

        return name, version

    def _append_agent_communication(
        self,
        *,
        role: str,
        content: str,
        conversation_id: int,
        metadata: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None,
    ) -> None:
        resolved_agent = agent_name
        if not resolved_agent:
            resolved_agent = self.agent_name if role == "assistant" else "user"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "conversation_id": conversation_id,
            "role": role,
            "agent_name": resolved_agent,
            "content": content,
            "metadata": metadata or {},
        }
        self.agent_interaction_logs.append(log_entry)
        if len(self.agent_interaction_logs) > 200:
            self.agent_interaction_logs = self.agent_interaction_logs[-200:]

    def _log_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event_type,
            "payload": payload,
        }
        self.orchestrator_logs.append(event)
        if len(self.orchestrator_logs) > 200:
            self.orchestrator_logs = self.orchestrator_logs[-200:]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        if not self._default_credential:
            return
        close_method = getattr(self._default_credential, "close", None)
        if not close_method:
            return
        try:
            result = close_method()
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # pylint: disable=broad-except
            pass

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        credential = self._default_credential
        if not credential:
            return
        close_method = getattr(credential, "close", None)
        if not close_method:
            return
        try:
            result = close_method()
            if asyncio.iscoroutine(result):
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(result)
                else:
                    loop.run_until_complete(result)
        except Exception:  # pylint: disable=broad-except
            pass


# Backward compatibility aliases -------------------------------------------------
ChatOrchestratorAgent = InventoryAssistantOrchestrator
ChatOrchestrator = InventoryAssistantOrchestrator
