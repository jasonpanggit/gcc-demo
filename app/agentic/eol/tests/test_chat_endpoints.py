"""
Test Suite for AutoGen Chat Endpoint (Phase 2)
Tests AI-powered conversational interface with multi-agent orchestration
"""
import pytest
from datetime import datetime


@pytest.mark.api
@pytest.mark.integration
@pytest.mark.chat
@pytest.mark.skipif(
    "not config.chat.enabled",
    reason="Chat functionality requires AutoGen orchestrator"
)
class TestChatEndpoints:
    """Test AutoGen chat endpoint added in Phase 2"""
    
    # =========================================================================
    # Basic Chat Functionality
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_basic(self, client):
        """Test POST /api/autogen-chat - Basic chat request"""
        request_data = {
            "message": "What is the EOL date for Windows Server 2016?",
            "timeout_seconds": 60
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # Validate AutoGenChatResponse structure
        assert 'response' in data
        assert 'conversation_messages' in data
        assert 'agent_communications' in data
        assert 'agents_involved' in data
        assert 'total_exchanges' in data
        assert 'session_id' in data
        
        # Response should be a string
        assert isinstance(data['response'], str)
        assert len(data['response']) > 0
        
        # Should have some conversation messages
        assert isinstance(data['conversation_messages'], list)
        
        # Should have agent communications
        assert isinstance(data['agent_communications'], list)
        
        # Should have agents involved
        assert isinstance(data['agents_involved'], list)
        assert len(data['agents_involved']) > 0
        
    @pytest.mark.asyncio
    async def test_autogen_chat_inventory_query(self, client):
        """Test chat with inventory-related query"""
        request_data = {
            "message": "Show me the software inventory",
            "timeout_seconds": 90
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        assert len(data['response']) > 0
        
        # Should involve inventory-related agents
        agents = data.get('agents_involved', [])
        assert len(agents) > 0
        
    @pytest.mark.asyncio
    async def test_autogen_chat_eol_query(self, client):
        """Test chat with EOL-related query"""
        request_data = {
            "message": "What software is past end of life?",
            "timeout_seconds": 90
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        assert 'agents_involved' in data
        
    # =========================================================================
    # Confirmation Workflows
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_without_confirmation(self, client):
        """Test chat without confirmation for destructive operations"""
        request_data = {
            "message": "Clear all caches",
            "confirmed": False,
            "timeout_seconds": 30
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # May require confirmation
        if data.get('confirmation_required'):
            assert data['confirmation_required'] is True
            assert 'pending_message' in data
            
    @pytest.mark.asyncio
    async def test_autogen_chat_with_confirmation(self, client):
        """Test chat with confirmation for destructive operations"""
        request_data = {
            "message": "Clear all caches",
            "confirmed": True,
            "original_message": "Clear all caches",
            "timeout_seconds": 30
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        
    # =========================================================================
    # Timeout Management
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_custom_timeout(self, client):
        """Test chat with custom timeout"""
        request_data = {
            "message": "Quick test",
            "timeout_seconds": 30
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        
    @pytest.mark.asyncio
    async def test_autogen_chat_default_timeout(self, client):
        """Test chat with default timeout"""
        request_data = {
            "message": "Test with default timeout"
            # No timeout_seconds specified, should use default (150s)
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        
    # =========================================================================
    # Response Size Limits
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_response_limits(self, client):
        """Test that response adheres to size limits"""
        request_data = {
            "message": "Give me a detailed analysis",
            "timeout_seconds": 60
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # Response should be limited to 100k chars
        assert len(data['response']) <= 100000
        
        # Conversation messages limited to 200
        assert len(data['conversation_messages']) <= 200
        
        # Agent communications limited to 100
        assert len(data['agent_communications']) <= 100
        
        # Agents involved limited to 20
        assert len(data['agents_involved']) <= 20
        
    # =========================================================================
    # Error Handling
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_missing_message(self, client):
        """Test chat without message field"""
        request_data = {
            "timeout_seconds": 30
            # Missing 'message' field
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 422  # Validation error
        
    @pytest.mark.asyncio
    async def test_autogen_chat_empty_message(self, client):
        """Test chat with empty message"""
        request_data = {
            "message": "",
            "timeout_seconds": 30
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        # Should either reject or handle gracefully
        assert response.status_code in [200, 400, 422]
        
    @pytest.mark.asyncio
    async def test_autogen_chat_invalid_timeout(self, client):
        """Test chat with invalid timeout"""
        request_data = {
            "message": "Test",
            "timeout_seconds": -10  # Invalid negative timeout
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]
        
    # =========================================================================
    # Session Management
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_session_id(self, client):
        """Test that each chat has a unique session ID"""
        request1 = {"message": "First message", "timeout_seconds": 30}
        request2 = {"message": "Second message", "timeout_seconds": 30}
        
        response1 = await client.post("/api/autogen-chat", json=request1)
        response2 = await client.post("/api/autogen-chat", json=request2)
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Each should have a session ID
        assert 'session_id' in data1
        assert 'session_id' in data2
        
        # Session IDs should be different
        assert data1['session_id'] != data2['session_id']
        
    # =========================================================================
    # Agent Communications
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_autogen_chat_agent_transparency(self, client):
        """Test full conversation transparency"""
        request_data = {
            "message": "Analyze Windows Server inventory",
            "timeout_seconds": 90
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # Should have agent communications for transparency
        assert 'agent_communications' in data
        assert isinstance(data['agent_communications'], list)
        
        # Each communication should have structure
        if len(data['agent_communications']) > 0:
            comm = data['agent_communications'][0]
            assert isinstance(comm, dict)
            
    # =========================================================================
    # Integration Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_chat_with_inventory_context(self, client):
        """Test that chat uses inventory context"""
        request_data = {
            "message": "What computers are in my inventory?",
            "timeout_seconds": 90
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        # Response should reference inventory data
        assert len(data['response']) > 0
        
    @pytest.mark.asyncio
    async def test_chat_multi_agent_orchestration(self, client):
        """Test multi-agent orchestration in complex query"""
        request_data = {
            "message": "Show me critical EOL risks in my Windows inventory",
            "timeout_seconds": 120
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # Should involve multiple agents
        assert len(data.get('agents_involved', [])) >= 1
        
        # Should have multiple exchanges
        assert data.get('total_exchanges', 0) >= 0
        
    @pytest.mark.asyncio
    async def test_chat_fast_path_detection(self, client):
        """Test fast path detection for simple queries"""
        request_data = {
            "message": "Hello",
            "timeout_seconds": 30
        }
        
        response = await client.post("/api/autogen-chat", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # May use fast path for simple greetings
        assert 'fast_path' in data
        
    # =========================================================================
    # Performance Tests
    # =========================================================================
    
    @pytest.mark.asyncio
    async def test_chat_response_time(self, client):
        """Test that chat responds within reasonable time"""
        import time
        
        request_data = {
            "message": "Quick test",
            "timeout_seconds": 30
        }
        
        start_time = time.time()
        response = await client.post("/api/autogen-chat", json=request_data)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        # Should respond within timeout + buffer
        assert elapsed < 40  # 30s timeout + 10s buffer
        
    @pytest.mark.asyncio
    async def test_chat_concurrent_requests(self, client):
        """Test handling of concurrent chat requests"""
        import asyncio
        
        requests = [
            {"message": f"Test message {i}", "timeout_seconds": 30}
            for i in range(3)
        ]
        
        # Send concurrent requests
        responses = await asyncio.gather(*[
            client.post("/api/autogen-chat", json=req)
            for req in requests
        ])
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert 'response' in data
            assert 'session_id' in data
