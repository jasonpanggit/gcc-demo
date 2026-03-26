# Multi-agent EOL analysis system

from .eol_orchestrator import EOLOrchestratorAgent
from .inventory_orchestrator import InventoryAssistantOrchestrator
from .endoflife_agent import EndOfLifeAgent
from .microsoft_agent import MicrosoftEOLAgent
from .redhat_agent import RedHatEOLAgent
from .ubuntu_agent import UbuntuEOLAgent
from .inventory_agent import InventoryAgent
from .azure_ai_agent import AzureAIAgentEOLAgent  # Modern replacement for Bing Search

__all__ = [
    'EOLOrchestratorAgent',
    'InventoryAssistantOrchestrator',
    'EndOfLifeAgent',
    'MicrosoftEOLAgent',
    'RedHatEOLAgent',
    'UbuntuEOLAgent',
    'InventoryAgent',
    'AzureAIAgentEOLAgent',
]
