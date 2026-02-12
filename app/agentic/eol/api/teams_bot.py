"""
Microsoft Teams Bot Integration
Provides webhook endpoint for Teams Bot Framework to enable chat interface with MCP Orchestrator
"""
import hashlib
import hmac
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import aiohttp
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel, Field, ConfigDict

from utils import get_logger
from utils.response_models import StandardResponse

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# CONVERSATION STATE MANAGEMENT
# ============================================================================

# In-memory conversation storage (keyed by conversation_id)
# For production, consider moving to Cosmos DB or Redis for persistence
_conversation_states: Dict[str, Dict[str, Any]] = {}
_MAX_CONVERSATION_HISTORY = 20  # Keep last 20 messages per conversation
_CONVERSATION_TTL_HOURS = 24  # Expire conversations after 24 hours


def _get_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """
    Get conversation history for a Teams conversation.

    Args:
        conversation_id: Teams conversation ID

    Returns:
        List of message dicts with 'role' and 'text' keys
    """
    if conversation_id not in _conversation_states:
        return []

    state = _conversation_states[conversation_id]

    # Check if conversation has expired
    last_updated = state.get("last_updated")
    if last_updated:
        age = datetime.utcnow() - last_updated
        if age > timedelta(hours=_CONVERSATION_TTL_HOURS):
            logger.info(f"Conversation {conversation_id} expired (age: {age}), resetting history")
            del _conversation_states[conversation_id]
            return []

    return state.get("history", [])


def _update_conversation_history(
    conversation_id: str,
    user_message: str,
    assistant_response: str
) -> None:
    """
    Update conversation history with a new exchange.

    Args:
        conversation_id: Teams conversation ID
        user_message: User's message
        assistant_response: Bot's response
    """
    if conversation_id not in _conversation_states:
        _conversation_states[conversation_id] = {
            "history": [],
            "last_updated": datetime.utcnow()
        }

    state = _conversation_states[conversation_id]
    history = state["history"]

    # Append new messages
    history.append({"role": "user", "text": user_message})
    history.append({"role": "assistant", "text": assistant_response})

    # Trim to max history length (keep most recent messages)
    if len(history) > _MAX_CONVERSATION_HISTORY:
        history[:] = history[-_MAX_CONVERSATION_HISTORY:]

    state["last_updated"] = datetime.utcnow()

    logger.info(f"Conversation {conversation_id}: {len(history)} messages in history")


def _clear_conversation_history(conversation_id: str) -> None:
    """Clear conversation history for a Teams conversation."""
    if conversation_id in _conversation_states:
        del _conversation_states[conversation_id]
        logger.info(f"Cleared conversation history for {conversation_id}")


def _format_conversation_context(history: List[Dict[str, str]]) -> str:
    """
    Format conversation history into a context string for the orchestrator.

    Args:
        history: List of message dicts with 'role' and 'text' keys

    Returns:
        Formatted context string
    """
    if not history:
        return ""

    context_parts = ["Here is our conversation history for context:"]
    for msg in history:
        role = msg["role"]
        text = msg["text"]
        if role == "user":
            context_parts.append(f"User: {text}")
        elif role == "assistant":
            context_parts.append(f"Assistant: {text}")

    return "\n".join(context_parts)


# ============================================================================
# TEAMS BOT MODELS
# ============================================================================

class TeamsBotActivity(BaseModel):
    """Teams Bot Activity model"""
    type: str
    id: Optional[str] = None
    timestamp: Optional[str] = None
    channelId: Optional[str] = None
    from_: Optional[Dict[str, Any]] = Field(None, alias='from')  # Use Field with alias for 'from'
    conversation: Optional[Dict[str, Any]] = None
    recipient: Optional[Dict[str, Any]] = None
    text: Optional[str] = None
    attachments: Optional[list] = None
    entities: Optional[list] = None
    channelData: Optional[Dict[str, Any]] = None
    action: Optional[str] = None
    replyToId: Optional[str] = None
    value: Optional[Dict[str, Any]] = None
    locale: Optional[str] = None
    localTimestamp: Optional[str] = None
    serviceUrl: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


# ============================================================================
# AUTHENTICATION & SECURITY
# ============================================================================

async def send_typing_indicator(
    service_url: str,
    conversation_id: str,
    bot_id: str,
    bot_password: str
) -> bool:
    """
    Send a typing indicator to Teams to show the bot is processing.

    Args:
        service_url: Teams service URL from activity
        conversation_id: Conversation ID from activity
        bot_id: Bot App ID
        bot_password: Bot App Password

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get Bot Framework access token using tenant-specific endpoint
        tenant_id = os.getenv("AZURE_TENANT_ID", "ffc83107-fcc0-4d2e-8798-d582da36505e")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": bot_id,
            "client_secret": bot_password,
            "scope": "https://api.botframework.com/.default"
        }

        async with aiohttp.ClientSession() as session:
            # Get access token
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }

            async with session.post(token_url, data=token_data, headers=headers) as token_response:
                if token_response.status != 200:
                    logger.error(f"Failed to get Bot Framework token for typing indicator: {token_response.status}")
                    return False

                token_json = await token_response.json()
                access_token = token_json.get("access_token")

                if not access_token:
                    logger.error("No access token in response for typing indicator")
                    return False

            # Send typing indicator activity
            typing_url = f"{service_url}/v3/conversations/{conversation_id}/activities"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            typing_activity = {
                "type": "typing",
                "from": {"id": bot_id}
            }

            async with session.post(typing_url, json=typing_activity, headers=headers) as typing_response:
                if typing_response.status not in (200, 201):
                    logger.error(f"Failed to send typing indicator: {typing_response.status}")
                    return False

                logger.info(f"Successfully sent typing indicator to Teams conversation {conversation_id}")
                return True

    except Exception as e:
        logger.error(f"Error sending typing indicator: {e}", exc_info=True)
        return False


async def send_teams_response(
    service_url: str,
    conversation_id: str,
    activity_id: str,
    response_text: str,
    bot_id: str,
    bot_password: str
) -> bool:
    """
    Send a response back to Teams via Bot Framework API.

    Args:
        service_url: Teams service URL from activity
        conversation_id: Conversation ID from activity
        activity_id: Activity ID to reply to
        response_text: Text to send
        bot_id: Bot App ID
        bot_password: Bot App Password

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get Bot Framework access token using tenant-specific endpoint
        # The bot app is registered in the tenant, so we use the tenant ID directly
        # Tenant ID from environment or use the known tenant
        tenant_id = os.getenv("AZURE_TENANT_ID", "ffc83107-fcc0-4d2e-8798-d582da36505e")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": bot_id,
            "client_secret": bot_password,
            "scope": "https://api.botframework.com/.default"
        }

        async with aiohttp.ClientSession() as session:
            # Get access token with proper headers
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }

            async with session.post(token_url, data=token_data, headers=headers) as token_response:
                if token_response.status != 200:
                    error_text = await token_response.text()
                    logger.error(f"Failed to get Bot Framework token: {token_response.status}")
                    logger.error(f"Token error response: {error_text}")
                    logger.error(f"Bot ID length: {len(bot_id)}, Password length: {len(bot_password)}")
                    return False

                token_json = await token_response.json()
                access_token = token_json.get("access_token")

                if not access_token:
                    logger.error("No access token in response")
                    logger.error(f"Token response: {token_json}")
                    return False

            # Send reply to conversation
            reply_url = f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            reply_body = {
                "type": "message",
                "from": {"id": bot_id},
                "text": response_text,
                "replyToId": activity_id
            }

            async with session.post(reply_url, json=reply_body, headers=headers) as reply_response:
                if reply_response.status not in (200, 201):
                    error_text = await reply_response.text()
                    logger.error(f"Failed to send reply: {reply_response.status} - {error_text}")
                    return False

                logger.info(f"Successfully sent reply to Teams conversation {conversation_id}")
                return True

    except Exception as e:
        logger.error(f"Error sending Teams response: {e}", exc_info=True)
        return False


def verify_teams_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """
    Verify Teams Bot Framework webhook signature.

    Args:
        request_body: Raw request body bytes
        signature: Signature from X-Microsoft-Teams-Signature header
        secret: Bot secret from environment

    Returns:
        True if signature is valid
    """
    try:
        if not secret:
            logger.warning("Teams bot secret not configured - skipping signature verification")
            return True  # In dev mode, allow unsigned requests

        # Calculate expected signature
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            request_body,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Error verifying Teams signature: {e}")
        return False


def create_teams_message_response(text: str, activity_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a Teams message response in Bot Framework format.

    Args:
        text: Message text to send
        activity_id: Original activity ID for reply

    Returns:
        Dict with Teams Bot Framework message structure
    """
    response = {
        "type": "message",
        "text": text,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    if activity_id:
        response["replyToId"] = activity_id

    return response


def create_adaptive_card_response(
    title: str,
    body_text: str,
    facts: Optional[Dict[str, str]] = None,
    actions: Optional[list] = None
) -> Dict[str, Any]:
    """
    Create an Adaptive Card response for Teams.

    Args:
        title: Card title
        body_text: Main body text
        facts: Optional key-value facts to display
        actions: Optional list of action buttons

    Returns:
        Dict with Adaptive Card structure
    """
    card = {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": title,
                "size": "Large",
                "weight": "Bolder"
            },
            {
                "type": "TextBlock",
                "text": body_text,
                "wrap": True
            }
        ]
    }

    # Add facts section if provided
    if facts:
        fact_set = {
            "type": "FactSet",
            "facts": [{"title": k, "value": v} for k, v in facts.items()]
        }
        card["body"].append(fact_set)

    # Add actions if provided
    if actions:
        card["actions"] = actions

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }]
    }


# ============================================================================
# TEAMS BOT WEBHOOK ENDPOINTS
# ============================================================================

@router.post("/api/teams-bot/messages")
async def handle_teams_bot_message(
    request: Request,
    x_microsoft_teams_signature: Optional[str] = Header(None, alias="X-Microsoft-Teams-Signature")
):
    """
    Webhook endpoint for Microsoft Teams Bot Framework.

    This endpoint receives messages from Teams users and forwards them to the
    MCP Orchestrator for processing.

    Required environment variables:
    - TEAMS_BOT_APP_ID: Azure Bot Service App ID
    - TEAMS_BOT_APP_PASSWORD: Azure Bot Service App Password (secret)

    Headers:
    - X-Microsoft-Teams-Signature: Signature for request verification

    Returns:
        Teams Bot Framework response
    """
    try:
        # Get request body
        request_body = await request.body()

        # Verify signature if secret is configured
        bot_secret = os.getenv("TEAMS_BOT_APP_PASSWORD")
        if bot_secret and x_microsoft_teams_signature:
            if not verify_teams_signature(request_body, x_microsoft_teams_signature, bot_secret):
                logger.warning("Invalid Teams bot signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse activity
        try:
            activity_data = json.loads(request_body)
            activity = TeamsBotActivity(**activity_data)
        except Exception as parse_error:
            logger.error(f"Error parsing Teams activity: {parse_error}")
            raise HTTPException(status_code=400, detail="Invalid activity format")

        logger.info(f"Received Teams bot activity: type={activity.type}, text={activity.text}")

        # Get bot credentials
        bot_app_id = os.getenv("TEAMS_BOT_APP_ID")
        bot_app_password = os.getenv("TEAMS_BOT_APP_PASSWORD")

        if not bot_app_id or not bot_app_password:
            logger.error("Teams bot credentials not configured")
            raise HTTPException(status_code=500, detail="Bot not configured")

        # Handle different activity types
        if activity.type == "message" and activity.text:
            # Handle special commands
            conversation_id = activity.conversation.get("id") if activity.conversation else None

            # Check for /clear command to reset conversation history
            if activity.text.strip().lower() in ["/clear", "/reset", "clear history"]:
                if conversation_id:
                    _clear_conversation_history(conversation_id)
                    clear_msg = "✅ Conversation history cleared. Starting fresh!"

                    if activity.serviceUrl and activity.id:
                        await send_teams_response(
                            service_url=activity.serviceUrl,
                            conversation_id=conversation_id,
                            activity_id=activity.id,
                            response_text=clear_msg,
                            bot_id=bot_app_id,
                            bot_password=bot_app_password
                        )

                    return {"status": "success", "message": "History cleared"}
                else:
                    logger.warning("Cannot clear history - no conversation ID")

            # Forward message to MCP orchestrator
            try:
                from agents.mcp_orchestrator import get_mcp_orchestrator

                orchestrator = await get_mcp_orchestrator()

                # Get user info for context
                user_name = "Teams User"
                if activity.from_ and activity.from_.get("name"):
                    user_name = activity.from_["name"]

                logger.info(f"Processing message from {user_name}: {activity.text[:50]}...")

                # Send typing indicator to show we're processing
                if activity.serviceUrl and conversation_id:
                    await send_typing_indicator(
                        service_url=activity.serviceUrl,
                        conversation_id=conversation_id,
                        bot_id=bot_app_id,
                        bot_password=bot_app_password
                    )

                # Get conversation history
                history = []
                if conversation_id:
                    history = _get_conversation_history(conversation_id)
                    logger.info(f"Retrieved {len(history)} messages from conversation history")

                # Build enhanced message with conversation context
                if history:
                    # Format conversation history as context
                    context = _format_conversation_context(history)
                    enhanced_message = f"{context}\n\nCurrent user message: {activity.text}"
                    logger.info(f"Enhanced message with {len(history)} historical messages")
                else:
                    enhanced_message = activity.text

                # Process message through orchestrator
                result = await orchestrator.process_message(enhanced_message)

                if result.get("success"):
                    response_text = result.get("response", "No response generated")

                    # Update conversation history with this exchange
                    if conversation_id:
                        _update_conversation_history(
                            conversation_id=conversation_id,
                            user_message=activity.text,  # Use original message, not enhanced
                            assistant_response=response_text
                        )

                    # Send response back to Teams
                    if activity.serviceUrl and conversation_id and activity.id:
                        success = await send_teams_response(
                            service_url=activity.serviceUrl,
                            conversation_id=conversation_id,
                            activity_id=activity.id,
                            response_text=response_text,
                            bot_id=bot_app_id,
                            bot_password=bot_app_password
                        )

                        if success:
                            logger.info("Response sent successfully to Teams")
                            return {"status": "success", "message": "Response sent"}
                        else:
                            logger.error("Failed to send response to Teams")
                            return {"status": "error", "message": "Failed to send response"}
                    else:
                        logger.error("Missing required activity fields for response")
                        return {"status": "error", "message": "Missing activity fields"}
                else:
                    error_msg = result.get("error", "Unknown error occurred")
                    logger.error(f"MCP orchestrator error: {error_msg}")

                    # Send error message to Teams
                    if activity.serviceUrl and conversation_id and activity.id:
                        await send_teams_response(
                            service_url=activity.serviceUrl,
                            conversation_id=conversation_id,
                            activity_id=activity.id,
                            response_text=f"❌ Error: {error_msg}",
                            bot_id=bot_app_id,
                            bot_password=bot_app_password
                        )

                    return {"status": "error", "message": error_msg}

            except Exception as mcp_error:
                logger.error(f"Error processing message with MCP orchestrator: {mcp_error}", exc_info=True)

                # Send error message to Teams
                if activity.serviceUrl and conversation_id and activity.id:
                    await send_teams_response(
                        service_url=activity.serviceUrl,
                        conversation_id=conversation_id,
                        activity_id=activity.id,
                        response_text="❌ Sorry, I encountered an error processing your request.",
                        bot_id=bot_app_id,
                        bot_password=bot_app_password
                    )

                return {"status": "error", "message": str(mcp_error)}

        elif activity.type == "conversationUpdate":
            # Bot was added to conversation
            members_added = activity.value.get("membersAdded", []) if activity.value else []
            bot_was_added = any(m.get("id") == bot_app_id for m in members_added)

            if bot_was_added and activity.serviceUrl and activity.conversation:
                welcome_message = """👋 **Welcome to the Azure MCP Orchestrator Bot!**

I can help you with:
• 🔍 Querying Azure resources
• 📊 Running Log Analytics queries
• 🛠️ Managing Azure Monitor workbooks
• 🏥 Checking resource health (SRE operations)
• 📈 Performance monitoring
• 🚨 Incident triage and troubleshooting

💬 **I remember our conversation context!** I can reference previous messages in our chat.

**Commands:**
- `/clear` or `/reset` - Clear conversation history and start fresh

**Examples:**
- "List my resource groups"
- "Check health of resource /subscriptions/..."
- "Show me critical EOL alerts"
- "Run a KQL query on Log Analytics"
"""

                conversation_id = activity.conversation.get("id")
                await send_teams_response(
                    service_url=activity.serviceUrl,
                    conversation_id=conversation_id,
                    activity_id=activity.id,
                    response_text=welcome_message,
                    bot_id=bot_app_id,
                    bot_password=bot_app_password
                )

                return {"status": "success", "message": "Welcome sent"}

        # Default response for other activity types
        return {"status": "success", "message": "Activity received"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Teams bot message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/teams-bot/status")
async def get_teams_bot_status():
    """
    Get Teams Bot configuration status and conversation statistics.

    Returns:
        Status information about Teams Bot configuration
    """
    try:
        bot_app_id = os.getenv("TEAMS_BOT_APP_ID")
        bot_app_password = os.getenv("TEAMS_BOT_APP_PASSWORD")

        configured = bool(bot_app_id and bot_app_password)

        # Calculate conversation statistics
        total_conversations = len(_conversation_states)
        total_messages = sum(
            len(state.get("history", []))
            for state in _conversation_states.values()
        )

        # Find oldest and newest conversations
        oldest_conversation = None
        newest_conversation = None
        if _conversation_states:
            sorted_states = sorted(
                _conversation_states.items(),
                key=lambda x: x[1].get("last_updated", datetime.min)
            )
            oldest_conversation = sorted_states[0][1].get("last_updated")
            newest_conversation = sorted_states[-1][1].get("last_updated")

        return StandardResponse.success_response(
            data=[{
                "configured": configured,
                "app_id_set": bool(bot_app_id),
                "app_password_set": bool(bot_app_password),
                "webhook_url": "/api/teams-bot/messages",
                "conversation_memory_enabled": True,
                "active_conversations": total_conversations,
                "total_messages_in_memory": total_messages,
                "max_history_per_conversation": _MAX_CONVERSATION_HISTORY,
                "conversation_ttl_hours": _CONVERSATION_TTL_HOURS,
                "oldest_conversation": oldest_conversation.isoformat() if oldest_conversation else None,
                "newest_conversation": newest_conversation.isoformat() if newest_conversation else None,
                "message": "Teams Bot is configured" if configured else "Teams Bot requires TEAMS_BOT_APP_ID and TEAMS_BOT_APP_PASSWORD"
            }],
            metadata={"service": "teams_bot"}
        )
    except Exception as e:
        logger.error(f"Error getting Teams bot status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/teams-bot/test")
async def test_teams_bot_message(test_message: str = "Hello from test"):
    """
    Test endpoint to simulate sending a message to the orchestrator.

    Args:
        test_message: Message to test with

    Returns:
        Response from MCP orchestrator
    """
    try:
        from agents.mcp_orchestrator import get_mcp_orchestrator

        orchestrator = await get_mcp_orchestrator()
        result = await orchestrator.process_message(test_message)

        return StandardResponse.success_response(
            data=[{
                "test_message": test_message,
                "response": result.get("response"),
                "success": result.get("success")
            }],
            metadata={"service": "teams_bot_test"}
        )
    except Exception as e:
        logger.error(f"Error testing Teams bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))
