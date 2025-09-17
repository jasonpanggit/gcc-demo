# Multi-agent EOL analysis system

from .eol_orchestrator import EOLOrchestratorAgent
from .chat_orchestrator import ChatOrchestratorAgent
from .endoflife_agent import EndOfLifeAgent
from .microsoft_agent import MicrosoftEOLAgent
from .redhat_agent import RedHatEOLAgent
from .ubuntu_agent import UbuntuEOLAgent
from .inventory_agent import InventoryAgent
from .azure_ai_agent import AzureAIAgentEOLAgent  # Modern replacement for Bing Search
from .websurfer_agent import WebsurferEOLAgent
from .oracle_agent import OracleEOLAgent
from .vmware_agent import VMwareEOLAgent
from .apache_agent import ApacheEOLAgent
from .nodejs_agent import NodeJSEOLAgent
from .postgresql_agent import PostgreSQLEOLAgent
from .php_agent import PHPEOLAgent
from .python_agent import PythonEOLAgent

__all__ = [
    'EOLOrchestratorAgent',
    'ChatOrchestratorAgent',
    'EndOfLifeAgent', 
    'MicrosoftEOLAgent',
    'RedHatEOLAgent',
    'UbuntuEOLAgent',
    'InventoryAgent',
    'AzureAIAgentEOLAgent',
    'WebsurferEOLAgent',
    'OracleEOLAgent',
    'VMwareEOLAgent',
    'ApacheEOLAgent',
    'NodeJSEOLAgent',
    'PostgreSQLEOLAgent',
    'PHPEOLAgent',
    'PythonEOLAgent'
]
