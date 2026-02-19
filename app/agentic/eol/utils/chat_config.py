"""
Chat Component Configuration
Centralized configuration for the unified chat component used across all interfaces.
"""

from typing import Dict, Any, Optional

# Chat mode configurations
CHAT_CONFIGS: Dict[str, Dict[str, Any]] = {
    'mcp': {
        'title': 'Conversation',
        'icon': 'fa-robot',
        'placeholder': 'Type your question about Azure resources...',
        'show_flow': True,
        'show_token_stats': True,
        'show_clear_button': True,
        'show_examples': True,
        'container_id': 'chat-history',
        'comms_container_id': 'communicationsStream',
        'examples_section': True,
        'server_selector': True,
        'tool_selector': True,
        'button_text': 'Send',
        'empty_message': 'Ask me anything about your Azure resources!',
        'empty_icon': 'fa-robot',
    },
    'sre': {
        'title': 'SRE Assistant',
        'icon': 'fa-heartbeat',
        'placeholder': 'Describe the issue or ask a question...',
        'show_flow': True,
        'show_token_stats': True,
        'show_clear_button': True,
        'show_examples': False,
        'container_id': 'chat-history',
        'comms_container_id': 'communicationsStream',
        'examples_section': False,
        'server_selector': False,
        'tool_selector': False,
        'button_text': 'Send',
        'empty_message': 'Describe your SRE issue or ask me anything!',
        'empty_icon': 'fa-heartbeat',
    },
    'inventory': {
        'title': 'Software Inventory Assistant',
        'icon': 'fa-server',
        'placeholder': 'Ask about software inventory, versions, or compliance...',
        'show_flow': True,
        'show_token_stats': True,
        'show_clear_button': True,
        'show_examples': False,
        'container_id': 'chat-history',
        'comms_container_id': 'communicationsStream',
        'examples_section': False,
        'server_selector': False,
        'tool_selector': False,
        'button_text': 'Ask',
        'empty_message': 'Ask me about your software inventory and compliance!',
        'empty_icon': 'fa-server',
    },
    'eol': {
        'title': 'EOL Analysis Assistant',
        'icon': 'fa-calendar-times',
        'placeholder': 'Enter product name or version to check EOL status...',
        'show_flow': False,
        'show_token_stats': False,
        'show_clear_button': True,
        'show_examples': False,
        'container_id': 'chat-history',
        'comms_container_id': 'communicationsStream',
        'examples_section': False,
        'server_selector': False,
        'tool_selector': False,
        'button_text': 'Search',
        'empty_message': 'Search for product End-of-Life information!',
        'empty_icon': 'fa-calendar-times',
    },
}


def get_chat_config(mode: str) -> Dict[str, Any]:
    """
    Get configuration for a specific chat mode.

    Args:
        mode: Chat mode identifier ('mcp', 'sre', 'inventory', 'eol')

    Returns:
        Configuration dictionary for the specified mode

    Raises:
        ValueError: If mode is not recognized
    """
    if mode not in CHAT_CONFIGS:
        raise ValueError(f"Unknown chat mode: {mode}. Available modes: {list(CHAT_CONFIGS.keys())}")

    return CHAT_CONFIGS[mode].copy()


def get_available_modes() -> list:
    """
    Get list of available chat modes.

    Returns:
        List of chat mode identifiers
    """
    return list(CHAT_CONFIGS.keys())


# Jinja2 helper functions
def chat_config_filter(mode: str, key: str, default: Any = None) -> Any:
    """
    Jinja2 filter to access chat config values.

    Usage in template:
        {{ 'mcp' | chat_config('title') }}
        {{ mode | chat_config('show_flow', false) }}

    Args:
        mode: Chat mode identifier
        key: Configuration key to retrieve
        default: Default value if key doesn't exist

    Returns:
        Configuration value or default
    """
    try:
        config = get_chat_config(mode)
        return config.get(key, default)
    except ValueError:
        return default


def chat_config_dict(mode: str) -> Dict[str, Any]:
    """
    Jinja2 function to get entire chat config as dictionary.

    Usage in template:
        {% set config = chat_config_dict('mcp') %}
        {{ config.title }}

    Args:
        mode: Chat mode identifier

    Returns:
        Full configuration dictionary
    """
    try:
        return get_chat_config(mode)
    except ValueError:
        return {}
