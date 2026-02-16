"""Agent message bus for inter-agent communication.

Provides pub/sub messaging, request/response patterns, and event streaming
for agent coordination.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger


logger = get_logger(__name__)


class Message:
    """Message container for agent communication."""

    def __init__(
        self,
        message_id: str,
        message_type: str,
        from_agent: str,
        to_agent: Optional[str],
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None
    ):
        """Initialize message.

        Args:
            message_id: Unique message identifier
            message_type: Message type (request, response, event)
            from_agent: Source agent ID
            to_agent: Destination agent ID (None for broadcast)
            payload: Message payload
            correlation_id: ID for request/response correlation
        """
        self.message_id = message_id
        self.message_type = message_type
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.payload = payload
        self.correlation_id = correlation_id
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """Create message from dictionary."""
        return cls(
            message_id=data["message_id"],
            message_type=data["message_type"],
            from_agent=data["from_agent"],
            to_agent=data.get("to_agent"),
            payload=data["payload"],
            correlation_id=data.get("correlation_id")
        )


class AgentMessageBus:
    """In-memory message bus for agent communication.

    Supports:
    - Pub/sub for events
    - Request/response for direct communication
    - Message routing by agent ID
    - Event streaming for UI updates
    """

    def __init__(self):
        """Initialize message bus."""
        self._subscribers: Dict[str, Set[Callable]] = defaultdict(set)
        self._agent_queues: Dict[str, asyncio.Queue] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._message_history: List[Message] = []
        self._max_history = 1000

        logger.info("Agent message bus initialized")

    async def subscribe(
        self,
        agent_id: str,
        message_types: Optional[List[str]] = None,
        callback: Optional[Callable] = None
    ) -> asyncio.Queue:
        """Subscribe an agent to messages.

        Args:
            agent_id: Agent identifier
            message_types: List of message types to subscribe to (None for all)
            callback: Optional callback function for message handling

        Returns:
            Message queue for the agent
        """
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue()
            logger.info(f"Agent {agent_id} subscribed to message bus")

        if callback:
            for msg_type in (message_types or ["*"]):
                self._subscribers[msg_type].add(callback)

        return self._agent_queues[agent_id]

    async def unsubscribe(self, agent_id: str) -> None:
        """Unsubscribe an agent from messages.

        Args:
            agent_id: Agent identifier
        """
        if agent_id in self._agent_queues:
            del self._agent_queues[agent_id]
            logger.info(f"Agent {agent_id} unsubscribed from message bus")

    async def publish_event(
        self,
        event_type: str,
        from_agent: str,
        payload: Dict[str, Any]
    ) -> str:
        """Publish an event to all subscribers.

        Args:
            event_type: Event type
            from_agent: Source agent ID
            payload: Event payload

        Returns:
            Message ID
        """
        message = Message(
            message_id=uuid.uuid4().hex,
            message_type=event_type,
            from_agent=from_agent,
            to_agent=None,  # Broadcast
            payload=payload
        )

        # Add to history
        self._add_to_history(message)

        # Notify subscribers
        await self._notify_subscribers(message)

        # Add to all agent queues
        for queue in self._agent_queues.values():
            try:
                await queue.put(message)
            except Exception as exc:
                logger.error(f"Failed to queue message: {exc}")

        logger.debug(
            f"Published event {event_type} from {from_agent} "
            f"to {len(self._agent_queues)} agents"
        )

        return message.message_id

    async def send_request(
        self,
        from_agent: str,
        to_agent: str,
        request_type: str,
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """Send a request and wait for response.

        Args:
            from_agent: Source agent ID
            to_agent: Destination agent ID
            request_type: Request type
            payload: Request payload
            timeout: Response timeout in seconds

        Returns:
            Response payload

        Raises:
            TimeoutError: If response not received within timeout
            ValueError: If destination agent not found
        """
        if to_agent not in self._agent_queues:
            raise ValueError(f"Agent {to_agent} not subscribed to message bus")

        # Create request message
        correlation_id = uuid.uuid4().hex
        message = Message(
            message_id=uuid.uuid4().hex,
            message_type=f"request.{request_type}",
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload,
            correlation_id=correlation_id
        )

        # Add to history
        self._add_to_history(message)

        # Create future for response
        response_future = asyncio.Future()
        self._pending_responses[correlation_id] = response_future

        # Send request
        await self._agent_queues[to_agent].put(message)

        logger.debug(
            f"Sent request {request_type} from {from_agent} to {to_agent} "
            f"(correlation: {correlation_id})"
        )

        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            # Clean up pending response
            del self._pending_responses[correlation_id]
            raise TimeoutError(
                f"Request {request_type} to {to_agent} timed out after {timeout}s"
            )

    async def send_response(
        self,
        from_agent: str,
        correlation_id: str,
        payload: Dict[str, Any]
    ) -> None:
        """Send a response to a previous request.

        Args:
            from_agent: Source agent ID
            correlation_id: Correlation ID from original request
            payload: Response payload
        """
        if correlation_id not in self._pending_responses:
            logger.warning(
                f"No pending request found for correlation ID {correlation_id}"
            )
            return

        # Create response message
        message = Message(
            message_id=uuid.uuid4().hex,
            message_type="response",
            from_agent=from_agent,
            to_agent=None,
            payload=payload,
            correlation_id=correlation_id
        )

        # Add to history
        self._add_to_history(message)

        # Resolve future
        future = self._pending_responses[correlation_id]
        if not future.done():
            future.set_result(payload)

        del self._pending_responses[correlation_id]

        logger.debug(
            f"Sent response from {from_agent} for correlation {correlation_id}"
        )

    async def send_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: Dict[str, Any]
    ) -> str:
        """Send a direct message (fire-and-forget).

        Args:
            from_agent: Source agent ID
            to_agent: Destination agent ID
            message_type: Message type
            payload: Message payload

        Returns:
            Message ID

        Raises:
            ValueError: If destination agent not found
        """
        if to_agent not in self._agent_queues:
            raise ValueError(f"Agent {to_agent} not subscribed to message bus")

        message = Message(
            message_id=uuid.uuid4().hex,
            message_type=message_type,
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload
        )

        # Add to history
        self._add_to_history(message)

        # Send to destination
        await self._agent_queues[to_agent].put(message)

        # Notify subscribers
        await self._notify_subscribers(message)

        logger.debug(
            f"Sent message {message_type} from {from_agent} to {to_agent}"
        )

        return message.message_id

    async def receive_message(
        self,
        agent_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Message]:
        """Receive next message for an agent.

        Args:
            agent_id: Agent identifier
            timeout: Optional timeout in seconds

        Returns:
            Next message or None if timeout
        """
        if agent_id not in self._agent_queues:
            raise ValueError(f"Agent {agent_id} not subscribed to message bus")

        queue = self._agent_queues[agent_id]

        try:
            if timeout:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                message = await queue.get()

            return message

        except asyncio.TimeoutError:
            return None

    async def _notify_subscribers(self, message: Message) -> None:
        """Notify subscribers of a message.

        Args:
            message: Message to notify about
        """
        # Notify type-specific subscribers
        callbacks = self._subscribers.get(message.message_type, set())

        # Notify wildcard subscribers
        callbacks.update(self._subscribers.get("*", set()))

        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            except Exception as exc:
                logger.error(f"Subscriber callback failed: {exc}")

    def _add_to_history(self, message: Message) -> None:
        """Add message to history.

        Args:
            message: Message to add
        """
        self._message_history.append(message)

        # Trim history if needed
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history:]

    def get_message_history(
        self,
        agent_id: Optional[str] = None,
        message_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get message history.

        Args:
            agent_id: Filter by agent ID (source or destination)
            message_type: Filter by message type
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
        """
        messages = self._message_history

        # Apply filters
        if agent_id:
            messages = [
                msg for msg in messages
                if msg.from_agent == agent_id or msg.to_agent == agent_id
            ]

        if message_type:
            messages = [
                msg for msg in messages
                if msg.message_type == message_type
            ]

        # Apply limit
        messages = messages[-limit:]

        return [msg.to_dict() for msg in messages]

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "subscribed_agents": len(self._agent_queues),
            "subscriber_callbacks": sum(len(s) for s in self._subscribers.values()),
            "pending_responses": len(self._pending_responses),
            "message_history_size": len(self._message_history),
            "queue_depths": {
                agent_id: queue.qsize()
                for agent_id, queue in self._agent_queues.items()
            }
        }

    async def clear_agent_queue(self, agent_id: str) -> int:
        """Clear all messages in an agent's queue.

        Args:
            agent_id: Agent identifier

        Returns:
            Number of messages cleared
        """
        if agent_id not in self._agent_queues:
            return 0

        queue = self._agent_queues[agent_id]
        count = 0

        while not queue.empty():
            try:
                queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"Cleared {count} messages from agent {agent_id} queue")

        return count


# Global message bus instance
_message_bus: Optional[AgentMessageBus] = None


def get_message_bus() -> AgentMessageBus:
    """Get or create the global message bus.

    Returns:
        Global AgentMessageBus instance
    """
    global _message_bus

    if _message_bus is None:
        _message_bus = AgentMessageBus()

    return _message_bus
