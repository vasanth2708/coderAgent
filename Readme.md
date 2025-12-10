# AI Coding Agent

An intelligent coding assistant built with LangGraph that helps developers read, understand, and modify codebases through natural language interactions.

## Features

- **Read & Explore**: Understand codebase structure and answer questions about code
- **Edit & Modify**: Make code changes based on natural language instructions
- **Run & React**: Execute commands (tests, linting) and automatically fix issues
- **Memory & Context**: Three-tier memory system (working/session/persistent)
- **Self-Correction**: Auto-fix loops that learn from test failures
- **Preferences**: Remember user preferences across sessions

## Architecture

The agent uses LangGraph to implement a state machine with the following trajectories:

- **Read**: Explore codebase, answer questions
- **Edit**: Plan and apply code changes
- **Run Command**: Execute shell commands (tests, linting, etc.)
- **Profile**: Manage user preferences

See [ARCHITECTURE.md](agent-v1/ARCHITECTURE.md) for detailed architecture documentation.

## Prerequisites

- Python 3.10 or higher
- DeepSeek API key (or OpenAI-compatible API)
- Ray (for parallel file operations)

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd coderAgent
```

### 2. Create Virtual Environment

```bash
python3 -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Optional - For Filesystem MCP Server:**
If you want to use the MCP filesystem server (recommended), ensure Node.js is installed:

```bash
# Check if Node.js is available
node --version
npx --version
```

The agent will automatically use the MCP filesystem server if Node.js is available, or fall back to direct file operations otherwise.

### 4. Set Up Environment Variables

Create a `.env` file in the `agent-v1` directory:

```bash
cd agent-v1
cat > .env << EOF
DEEPSEEK_API_KEY=your-api-key-here
EOF
```

Or for OpenAI:

```bash
cat > .env << EOF
OPENAI_API_KEY=your-api-key-here
EOF
```

**Note**: The agent is configured for DeepSeek by default. To use OpenAI, modify `agent-v1/mcps/llm_config.py`.

### 5. Verify Sample Project

The agent works with the `sampleProject` directory. Ensure it exists and contains:

```
sampleProject/
├── main.py
├── models.py
├── routes/
│   ├── tasks.py
│   └── users.py
├── utils/
│   └── helpers.py
└── tests/
    └── test_tasks.py
```

Install sample project dependencies:

```bash
cd sampleProject
pip install -r requirements.txt
```

## Usage

### Start the Agent

```bash
cd agent-v1
python main.py
```

## Demo Video - https://www.loom.com/share/a2ff88a6419a48d9a8b90a6f48637f70

### Example Interactions

```
You> What files are in this project?
Agent> [Lists files and describes each]

You> Show me how tasks are created
Agent> [Reads routes/tasks.py and explains the create endpoint]

You> Add validation to reject empty task titles
Agent> [Plans edits, shows preview]
You> approve
Agent> [Applies edits, runs tests]

You> Run the tests
Agent> [Runs pytest, shows results]

You> Fix the failing test
Agent> [Enters auto-fix loop, attempts fixes]

You> Always add docstrings when you edit functions. Remember that.
Agent> [Saves preference to persistent memory]
```

### Commands

- `approve` - Apply pending edits and run tests
- `exit` or `quit` - Stop the agent

## Project Structure

```
coderAgent/
├── agent-v1/              # Main agent code
│   ├── main.py            # Entry point
│   ├── graph.py           # LangGraph state machine
│   ├── state.py           # Agent state definition
│   ├── mcps/              # Tool modules with MCP protocol integration
│   │   ├── filesystem_mcp.py      # File operations (MCP-enabled)
│   │   ├── execution_mcp.py       # Command execution (MCP-enabled)
│   │   ├── mcp_client.py          # MCP client infrastructure
│   │   ├── mcp_adapter.py         # MCP adapter layer
│   │   ├── mcp_execution_server.py # Custom execution MCP server
│   │   ├── edit_mcp.py            # Edit planning
│   │   ├── read_mcp.py            # Context retrieval
│   │   ├── intent_mcp.py          # Intent classification
│   │   └── memory_mcp.py          # Memory management
│   ├── ARCHITECTURE.md    # Architecture documentation
│   └── .coder_agent_memory.json  # Persistent memory (auto-created)
├── sampleProject/         # Target codebase for agent
└── README.md             # This file
```

## Configuration

### LLM Configuration

Edit `agent-v1/mcps/llm_config.py` to change:
- API provider (DeepSeek, OpenAI, etc.)
- Model name
- Temperature
- API base URL

### Memory Configuration

Memory is stored in `.coder_agent_memory.json`. This file is auto-created and contains:
- User preferences
- Query cache (invalidated on code changes)
- Execution logs

### Timeout Configuration

Command execution timeout is set in `agent-v1/mcps/execution_mcp.py`:
```python
COMMAND_TIMEOUT = 30  # seconds
```

## Troubleshooting

### Ray Initialization Errors

If you see Ray metrics exporter errors, they are automatically suppressed. The agent initializes Ray with minimal logging.

### Memory File Issues

If `.coder_agent_memory.json` becomes corrupted:
```bash
rm agent-v1/.coder_agent_memory.json
# Agent will create a new one on next run
```

### API Key Not Found

Ensure your `.env` file is in `agent-v1/` directory and contains:
```
DEEPSEEK_API_KEY=your-key-here
```

### Import Errors

Ensure you're in the `agent-v1` directory when running:
```bash
cd agent-v1
python main.py
```

## Development

### Adding New Trajectories

See [ARCHITECTURE.md](agent-v1/ARCHITECTURE.md) for instructions on adding new trajectories to the state machine.

### Testing

Run the sample project tests:
```bash
cd sampleProject
pytest
```

### Logging

Logs are written to `agent-v1/agent.log`. Set log level in `agent-v1/mcps/logger_config.py`.

## Limitations

- Currently works with Python codebases (can be extended)
- Command execution timeout: 30 seconds
- Context window: 50,000 characters (auto-truncated)
- Conversation history: Last 10 items

## MCP (Model Context Protocol) Integration

The agent now includes **MCP protocol integration** with tool discovery and execution via MCP servers. The implementation includes:

### MCP Servers Integrated

1. **Filesystem MCP Server** (`@modelcontextprotocol/server-filesystem`)
   - Provides secure file operations (read, write, list)
   - Uses the community Node.js-based filesystem server
   - Automatically falls back to direct file operations if MCP server is unavailable

2. **Execution MCP Server** (Custom Python implementation)
   - Provides command execution capabilities
   - Custom MCP server implemented in Python
   - Located at `agent-v1/mcps/mcp_execution_server.py`

### How It Works

- **Tool Discovery**: On startup, the agent discovers available tools from registered MCP servers
- **Automatic Fallback**: If MCP servers are unavailable, the agent falls back to direct tool implementations
- **Protocol Communication**: Tools are called via JSON-RPC 2.0 protocol over stdio

### Prerequisites for MCP

**For Filesystem Server** (optional):
- Node.js and `npx` must be installed
- The filesystem server will be automatically started with access to the `sampleProject` directory

**For Execution Server**:
- No additional dependencies (pure Python)

If Node.js is not available, the agent will use direct file operations instead of the MCP filesystem server, but the execution MCP server will still work.

### MCP Architecture

The MCP implementation includes:
- `mcps/mcp_client.py`: MCP client infrastructure for connecting to servers
- `mcps/mcp_adapter.py`: Adapter layer that routes tool calls through MCP protocol
- `mcps/mcp_execution_server.py`: Custom execution MCP server
- Updated tool modules that check for MCP availability and use it when possible

## Future Development

The following improvements are planned for future versions:

### Enhanced Command Execution
- **Improved run command handler**: More robust command parsing and execution with better error handling, support for complex command pipelines, and improved timeout management
- **Command history and replay**: Track executed commands and allow replaying previous commands
- **Interactive command execution**: Support for commands that require user input or interactive sessions

### Code Understanding & RAG
- **RAG (Retrieval-Augmented Generation) for code**: Implement semantic code search and retrieval to improve code understanding and context awareness. This was intentionally omitted from the initial version to keep complexity manageable, but would significantly enhance the agent's ability to find and understand relevant code patterns
- **Code embedding and similarity search**: Better semantic matching of code patterns and functions
- **Cross-file dependency analysis**: Understand relationships between files and modules

### Additional Enhancements
- **Multi-language support**: Extend beyond Python to support JavaScript, TypeScript, Go, Rust, and other languages
- **Advanced refactoring**: Support for large-scale refactorings across multiple files with dependency tracking
- **Test generation**: Automatically generate unit tests based on code analysis
- **Code quality metrics**: Integration with linters, formatters, and code quality tools
- **Version control integration**: Better integration with Git for change tracking and rollback
- **Streaming responses**: Real-time streaming of LLM responses for better user experience


