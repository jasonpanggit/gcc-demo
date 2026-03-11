"""
Unit tests for Inventory Orchestrator.

Tests cover:
- Request handling with confirmation semantics
- Communication history tracking
- Lifecycle management
- Error handling

Created: 2026-02-27 (Phase 1, Task 2.3)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agents.inventory_orchestrator import InventoryAssistantOrchestrator


@pytest.fixture
def factory_inventory_orchestrator():
    def _factory():
        orchestrator = InventoryAssistantOrchestrator()
        orchestrator._chat_client = MagicMock()
        return orchestrator

    return _factory


@pytest.mark.unit
@pytest.mark.orchestrator
@pytest.mark.asyncio
class TestInventoryOrchestrator:
    """Test suite for Inventory Orchestrator."""

    async def test_respond_with_confirmation_simple_message(self, factory_inventory_orchestrator):
        """Test basic message processing without confirmation.

        Scenario: User sends simple inventory query
        Expected: Orchestrator processes and returns response
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()
        message = "Show me OS inventory"

        # Mock internal methods to avoid complex dependencies
        with patch.object(orchestrator, '_ensure_chat_client', new_callable=AsyncMock) as mock_client:
            mock_client.return_value = True

            with patch.object(orchestrator, '_execute_inventory_summary', new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = {"success": True, "data": {}}

                # Act
                result = await orchestrator.respond_with_confirmation(message)

                # Assert
                assert result is not None
                assert "assistant_reply" in result or "success" in result or "response" in result

    async def test_respond_with_confirmation_confirmed_action(self, factory_inventory_orchestrator):
        """Test message processing with confirmed=True.

        Scenario: User confirms a previous action
        Expected: Orchestrator processes confirmed action
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()
        message = "yes"
        original_message = "Show me EOL data"

        # Mock internal methods
        with patch.object(orchestrator, '_ensure_chat_client', new_callable=AsyncMock) as mock_client:
            mock_client.return_value = True

            with patch.object(orchestrator, '_execute_os_inventory_eol_checks', new_callable=AsyncMock) as mock_eol:
                mock_eol.return_value = {"success": True, "data": {}}

                # Act
                result = await orchestrator.respond_with_confirmation(
                    message,
                    confirmed=True,
                    original_message=original_message
                )

                # Assert
                assert result is not None

    async def test_respond_with_confirmation_declined_action(self, factory_inventory_orchestrator):
        """Test message processing with confirmed=False and original_message.

        Scenario: User declines a previous action
        Expected: Orchestrator returns declined response
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()
        message = "no"
        original_message = "Show me EOL data"

        # Act
        result = await orchestrator.respond_with_confirmation(
            message,
            confirmed=False,
            original_message=original_message
        )

        # Assert
        assert result is not None
        assert "assistant_reply" in result or "response" in result

    async def test_get_agent_communications(self, factory_inventory_orchestrator):
        """Test retrieval of agent communication history.

        Scenario: Retrieve communication logs
        Expected: Returns list of communication events
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()

        # Act
        result = await orchestrator.get_agent_communications()

        # Assert
        assert isinstance(result, list)

    async def test_clear_communications(self, factory_inventory_orchestrator):
        """Test clearing of communication history.

        Scenario: Clear all communications
        Expected: Returns success and clears history
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()

        # Act
        result = await orchestrator.clear_communications()

        # Assert
        assert result is not None
        assert result.get("success") is True or "cleared" in str(result).lower()

    async def test_orchestrator_lifecycle_aclose(self, factory_inventory_orchestrator):
        """Test orchestrator properly closes resources.

        Scenario: Orchestrator is closed
        Expected: All resources are cleaned up
        """
        # Arrange
        orchestrator = factory_inventory_orchestrator()

        # Act
        await orchestrator.aclose()

        # Assert - orchestrator should be in cleaned state
        assert orchestrator is not None  # Basic check that aclose didn't crash

    async def test_should_use_software_inventory_fast_path_for_direct_inventory_question(self):
        orchestrator = InventoryAssistantOrchestrator()

        result = orchestrator._should_use_software_inventory_fast_path(
            "what software do i have in inventory",
            {
                "metadata": {
                    "requested_intents": {
                        "is_inventory_query": True,
                        "is_software_inventory_query": True,
                        "is_os_inventory_query": False,
                        "is_eol_query": False,
                        "is_approaching_eol_query": False,
                    }
                }
            },
        )

        assert result is True

    async def test_build_software_inventory_fast_path_response_renders_summary_and_tables(self):
        orchestrator = InventoryAssistantOrchestrator()

        response = orchestrator._build_software_inventory_fast_path_response(
            {
                "metadata": {
                    "inventory_summary": {
                        "software": {
                            "total_software": 131,
                            "total_computers": 2,
                            "top_publishers": [
                                {"publisher": "Microsoft", "installations": 88},
                                {"publisher": "Adobe", "installations": 12},
                            ],
                            "top_categories": [
                                {"category": "Application", "installations": 90},
                            ],
                        }
                    },
                    "software_inventory": {
                        "count": 131,
                        "from_cache": True,
                        "top_software": [
                            ["Microsoft Edge", "15", "2"],
                            ["Microsoft Visual C++", "10", "2"],
                        ],
                    },
                }
            }
        )

        assert "<h2>Software Inventory</h2>" in response
        assert "Current inventory (last 90 days): <strong>131</strong> software items across <strong>2</strong> computers." in response
        assert "Top Installed Software" in response
        assert "Microsoft Edge" in response
        assert "Top Publishers" in response
        assert "Top Categories" in response

    async def test_should_use_eol_lookup_fast_path_for_direct_eol_question(self):
        orchestrator = InventoryAssistantOrchestrator()

        result = orchestrator._should_use_eol_lookup_fast_path(
            "What is the EOL date of Windows Server 2016?",
            {
                "metadata": {
                    "requested_intents": {
                        "is_inventory_query": False,
                        "is_software_inventory_query": False,
                        "is_os_inventory_query": False,
                        "is_eol_query": True,
                        "is_approaching_eol_query": False,
                    },
                    "eol_lookup": {
                        "software": "Windows Server",
                        "version": "2016",
                        "success": True,
                        "eol_date": "2027-01-12",
                    },
                }
            },
        )

        assert result is True

    async def test_build_eol_lookup_fast_path_response_renders_direct_answer(self):
        orchestrator = InventoryAssistantOrchestrator()

        response = orchestrator._build_eol_lookup_fast_path_response(
            {
                "metadata": {
                    "eol_lookup": {
                        "software": "Windows Server",
                        "version": "2016",
                        "success": True,
                        "eol_date": "2027-01-12",
                        "status": "supported",
                        "support_status": "Extended Support",
                        "risk_level": "medium",
                        "days_until_eol": 309,
                        "agent_used": "microsoft",
                        "confidence": 0.98,
                    }
                }
            }
        )

        assert "<h2>End of Life Date for Windows Server 2016</h2>" in response
        assert "Windows Server 2016</strong> reaches end of life on <strong>2027-01-12</strong>" in response
        assert "Extended Support" in response
        assert "Days until EOL: 309" in response
        assert "microsoft" in response

    @pytest.mark.placeholder
    async def test_respond_timeout_handling(self, factory_inventory_orchestrator):
        """Test timeout handling in respond_with_confirmation.

        Scenario: Operation times out
        Expected: Returns timeout error gracefully

        NOTE: Placeholder for Phase 2 (timeout implementation)
        """
        pytest.skip("Timeout handling not yet tested (Phase 2)")

    @pytest.mark.placeholder
    async def test_conversation_history_persistence(self, factory_inventory_orchestrator):
        """Test conversation history is maintained across calls.

        Scenario: Multiple sequential messages
        Expected: History grows and is accessible

        NOTE: Placeholder for Phase 2 (history validation)
        """
        pytest.skip("Conversation history validation not yet tested (Phase 2)")
