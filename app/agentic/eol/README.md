# 🔄 End-of-Life (EOL) Multi-Agent Analysis Application

A sophisticated software End-of-Life (EOL) analysis application that combines Azure Log Analytics inventory data with intelligent multi-agent AI systems to provide comprehensive software lifecycle insights and risk assessment.

## 🚀 Overview

This application leverages a multi-agent architecture to automatically discover, analyze, and report on software end-of-life status across your IT infrastructure. It integrates Azure Log Analytics for inventory data with specialized EOL agents for accurate lifecycle information.

### Key Features

- **🔍 Intelligent Inventory Discovery**: Automated software and OS inventory from Azure Log Analytics
- **🤖 Multi-Agent EOL Analysis**: Specialized agents for different software vendors (Microsoft, Red Hat, Ubuntu, Oracle, etc.)
- **💬 AI-Powered Chat Interface**: Interactive EOL analysis using Azure OpenAI and AutoGen framework
- **📊 Real-time Risk Assessment**: Automatic categorization of EOL risks (Critical, High, Medium, Low)
- **🎯 Smart Search**: Intelligent EOL lookups with confidence scoring and early termination
- **⚡ Performance Optimized**: Caching, parallel processing, and load management

## 🏗️ Architecture

### Multi-Agent System

The application uses a sophisticated multi-agent architecture:

#### Core Orchestrators
- **`ChatOrchestratorAgent`**: Manages conversational AI interactions and AutoGen multi-agent conversations
- **`EOLOrchestratorAgent`**: Coordinates EOL data gathering from specialized agents

#### Inventory Agents
- **`InventoryAgent`**: Provides summary and coordination for inventory data
- **`OSInventoryAgent`**: Retrieves operating system inventory from Azure Log Analytics
- **`SoftwareInventoryAgent`**: Retrieves software inventory from Azure Log Analytics

#### EOL Specialist Agents
- **`MicrosoftEOLAgent`**: Windows, SQL Server, Office lifecycle data
- **`RedHatEOLAgent`**: RHEL, CentOS, Fedora lifecycle information
- **`UbuntuEOLAgent`**: Ubuntu and Canonical product lifecycles
- **`EndOfLifeAgent`**: General EOL data from endoflife.date API
- **`OracleEOLAgent`**: Oracle database and middleware lifecycles
- **`VMwareEOLAgent`**: VMware product lifecycle data
- **`ApacheEOLAgent`**: Apache web server and components
- **`NodeJSEOLAgent`**: Node.js runtime lifecycle
- **`PostgreSQLEOLAgent`**: PostgreSQL database lifecycle
- **`PHPEOLAgent`**: PHP runtime lifecycle
- **`PythonEOLAgent`**: Python interpreter lifecycle

#### Supporting Agents
- **`OpenAIAgent`**: Azure OpenAI integration for AI-powered analysis
- **`BingEOLAgent`**: Web search fallback for EOL information

### Intelligent Routing

The system uses intelligent agent routing based on:
- **Software Vendor Detection**: Automatically routes queries to the most appropriate specialist agents
- **Confidence Scoring**: Each agent provides confidence scores for their results
- **Early Termination**: High-confidence results (≥90%) terminate searches early for efficiency
- **Fallback Mechanisms**: Multiple agents provide redundancy and coverage

## 🛠️ Technology Stack

### Backend
- **FastAPI**: High-performance async web framework
- **Python 3.9+**: Core runtime environment
- **Azure SDK**: Integration with Azure services
- **AutoGen 0.7.x**: Multi-agent conversation framework
- **Pydantic**: Data validation and serialization

### AI & Analytics
- **Azure OpenAI**: GPT-4 powered conversational AI
- **Azure Log Analytics**: Inventory data source
- **Custom ML Models**: EOL prediction and risk assessment

### Data & Caching
- **Azure Cosmos DB**: Communication logs and session data
- **In-memory Caching**: Performance optimization
- **JSON Processing**: Data transformation and aggregation

### Frontend
- **Jinja2 Templates**: Server-side rendering
- **HTML5/CSS3/JavaScript**: Interactive web interface
- **Bootstrap**: Responsive UI framework
- **Chart.js**: Data visualization

## 📁 Project Structure

```
app/agentic/eol/
├── agents/                    # Multi-agent system
│   ├── chat_orchestrator.py   # Conversational AI orchestrator
│   ├── eol_orchestrator.py    # EOL analysis orchestrator
│   ├── inventory_agent.py     # Inventory coordination
│   ├── os_inventory_agent.py  # OS inventory from Log Analytics
│   ├── software_inventory_agent.py # Software inventory
│   ├── microsoft_agent.py     # Microsoft EOL specialist
│   ├── redhat_agent.py        # Red Hat EOL specialist
│   ├── ubuntu_agent.py        # Ubuntu EOL specialist
│   ├── endoflife_agent.py     # General EOL API agent
│   ├── openai_agent.py        # Azure OpenAI integration
│   └── [other specialist agents]
├── templates/                 # Web interface templates
│   ├── chat.html             # Conversational AI interface
│   ├── eol.html              # EOL analysis dashboard
│   ├── inventory.html        # Inventory management
│   └── agents.html           # Agent status monitoring
├── static/                   # Static web assets
├── utils/                    # Utility modules
│   ├── cache_stats_manager.py # Performance monitoring
│   ├── cosmos_cache.py       # Cosmos DB integration
│   └── config.py            # Configuration management
├── deploy/                   # Deployment configuration
├── main.py                   # FastAPI application
└── requirements.txt          # Python dependencies
```

## 🚀 Getting Started

### Prerequisites

- **Azure Subscription**: Required for Log Analytics and OpenAI services
- **Python 3.9+**: Core runtime requirement
- **Azure CLI**: For authentication and deployment
- **Log Analytics Workspace**: For inventory data

### Environment Variables

Create a `.env` file or set these environment variables:

```bash
# Azure Authentication
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TENANT_ID=your-tenant-id

# Azure Services
LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id
AZURE_OPENAI_ENDPOINT=your-openai-endpoint
AZURE_OPENAI_API_KEY=your-openai-key
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Application Configuration
ENVIRONMENT=development
PYTHONUNBUFFERED=1
WEBSITES_PORT=8000
```

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd LinkLandingZone/app/agentic/eol
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure authentication**:
   ```bash
   az login
   ```

4. **Run the application**:
   ```bash
   python main.py
   ```

5. **Access the web interface**:
   - Navigate to `http://localhost:8000`
   - Try the different interfaces:
     - `/chat` - Conversational AI interface
     - `/eol` - EOL analysis dashboard
     - `/inventory` - Inventory management
     - `/agents` - Agent monitoring

## 🔧 Configuration

### Agent Configuration

The multi-agent system can be configured through environment variables:

```bash
# Agent Timeouts
AGENT_TIMEOUT_SECONDS=30
EOL_SEARCH_TIMEOUT=15

# Cache Configuration
CACHE_TTL_SECONDS=3600
MAX_CACHE_SIZE=1000

# Concurrency Limits
MAX_CONCURRENT_AGENTS=10
MAX_PARALLEL_REQUESTS=5
```

### Smart Search Configuration

The intelligent EOL search system supports:

- **Confidence Thresholds**: Configurable minimum confidence levels
- **Early Termination**: High-confidence results stop additional searches
- **Agent Prioritization**: Vendor-specific agents prioritized over generic ones
- **Fallback Strategies**: Multiple search strategies for comprehensive coverage

## 📊 API Endpoints

### Inventory Endpoints
- `GET /api/inventory` - Get software inventory with EOL analysis
- `GET /api/os-inventory` - Get operating system inventory
- `GET /api/inventory-summary` - Get inventory summary statistics

### EOL Analysis Endpoints
- `GET /api/eol/{software}` - Get EOL data for specific software
- `POST /api/analyze` - Comprehensive EOL risk analysis
- `GET /api/agents/status` - Agent health and performance metrics

### Chat & Conversation Endpoints
- `POST /api/chat` - Interactive AI-powered EOL analysis
- `GET /api/chat/history` - Conversation history
- `POST /api/autogen/start` - Start multi-agent conversation

### Utility Endpoints
- `GET /api/health` - Application health check
- `GET /api/cache/stats` - Cache performance statistics
- `POST /api/cache/clear` - Clear application caches

## 🎯 Smart EOL Search

The application implements a sophisticated 3-strategy search approach:

### Strategy 1: Exact Match
- Precise product name and version matching
- Highest confidence results (95%+)
- Early termination for efficient processing

### Strategy 2: Name-Only Search
- Searches using product name without version
- Handles cases where version formats differ
- Medium confidence results (80-95%)

### Strategy 3: Normalized Search
- Fallback search with normalized product names
- Handles variations in naming conventions
- Lower confidence results (60-80%)

### Confidence-Based Early Return

- **≥90% Confidence**: Immediate return for vendor-specific agents
- **≥80% Confidence**: Early return for general searches
- **<80% Confidence**: Continue to next strategy
- **Multiple Agents**: Best result across all agents returned

## 🔍 Key Features Deep Dive

### 1. Inventory Enhancement
- **Product Extraction**: Intelligent parsing of inventory data
- **Version Matching**: Precise product-to-line matching using name+version validation
- **EOL Integration**: Automatic enhancement of inventory with EOL information
- **Performance Optimization**: Parallel processing and caching

### 2. Risk Assessment
- **Critical**: Software already end-of-life
- **High**: EOL within 6 months
- **Medium**: EOL within 2 years
- **Low**: Currently supported with long runway

### 3. Agent Monitoring
- **Performance Metrics**: Response times, success rates, cache hit ratios
- **Health Checks**: Agent availability and error rates
- **Communication Logs**: Detailed agent interaction history
- **Load Balancing**: Intelligent request distribution

### 4. Conversational AI
- **Natural Language**: Ask questions about your software inventory
- **Multi-Agent Collaboration**: Different agents provide specialized insights
- **Context Awareness**: Maintains conversation context and history
- **Actionable Insights**: Specific recommendations for EOL management

## 🚀 Deployment

### Azure App Service

The application is designed for Azure App Service deployment:

```bash
# Deploy using the provided script
cd deploy/
./deploy-app.sh
```

### Docker Deployment

```bash
# Build the container
docker build -t eol-app .

# Run the container
docker run -p 8000:8000 \
  -e LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id \
  -e AZURE_OPENAI_ENDPOINT=your-endpoint \
  eol-app
```

### Configuration Files

- `deploy/appsettings.json` - Default settings
- `deploy/appsettings.production.json` - Production overrides
- `deploy/appsettings.development.json` - Development settings

## 📈 Performance & Monitoring

### Metrics Tracked
- **Response Times**: Agent and endpoint performance
- **Cache Hit Rates**: Caching efficiency
- **Error Rates**: Reliability metrics
- **Throughput**: Requests per second

### Optimization Features
- **Intelligent Caching**: Multi-level caching strategy
- **Parallel Processing**: Concurrent agent execution
- **Load Management**: Request throttling and queuing
- **Early Termination**: Confidence-based search optimization

## 🤝 Contributing

### Development Setup

1. **Install development dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio
   ```

2. **Run tests**:
   ```bash
   pytest
   ```

3. **Code formatting**:
   ```bash
   black .
   isort .
   ```

### Adding New EOL Agents

To add a new EOL specialist agent:

1. Create a new agent class inheriting from `BaseEOLAgent`
2. Implement required methods: `get_eol_data()`, `search_eol()`
3. Add agent to `EOLOrchestratorAgent.__init__()`
4. Update routing logic in `_route_to_agents()`
5. Add tests for the new agent

### Architecture Guidelines

- **Async/Await**: All I/O operations must be asynchronous
- **Error Handling**: Comprehensive exception handling with graceful degradation
- **Logging**: Structured logging with correlation IDs
- **Caching**: Implement caching for expensive operations
- **Configuration**: Use environment variables for configuration

## 📄 License

This project is part of the LinkLandingZone infrastructure automation toolkit.

## 🆘 Support & Troubleshooting

### Common Issues

1. **Azure Authentication Failures**:
   - Verify Azure CLI login: `az account show`
   - Check service principal permissions
   - Validate environment variables

2. **Log Analytics Connection Issues**:
   - Verify workspace ID and permissions
   - Check network connectivity
   - Validate KQL queries

3. **Agent Performance Issues**:
   - Check agent status: `GET /api/agents/status`
   - Review cache statistics: `GET /api/cache/stats`
   - Monitor application logs

### Performance Tuning

- **Increase Cache TTL**: For more stable environments
- **Adjust Concurrency Limits**: Based on Azure quotas
- **Optimize KQL Queries**: For faster inventory retrieval
- **Configure Agent Timeouts**: Based on network conditions

### Monitoring & Alerts

The application provides comprehensive monitoring through:
- Azure Application Insights integration
- Custom performance metrics
- Health check endpoints
- Structured logging for troubleshooting

---

For detailed deployment instructions and advanced configuration, see the [deployment README](deploy/README.md).
