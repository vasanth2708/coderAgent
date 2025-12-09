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

If `requirements.txt` doesn't exist, install manually:

```bash
pip install langgraph langchain langchain-openai langchain-core pydantic ray python-dotenv
```

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
│   ├── mcps/              # MCP modules (tool integrations)
│   │   ├── filesystem_mcp.py
│   │   ├── execution_mcp.py
│   │   ├── edit_mcp.py
│   │   ├── read_mcp.py
│   │   ├── intent_mcp.py
│   │   └── memory_mcp.py
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

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

