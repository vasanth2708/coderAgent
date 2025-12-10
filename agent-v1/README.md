# AI Coding Agent (agent-v1)

## Overview
LangGraph-based coding agent with real MCP (Model Context Protocol) integration, automatic code editing with approval flow, and intelligent retry logic.

## Features
- **Real MCP Integration**: Filesystem and execution servers via JSON-RPC
- **Approval Flow**: User approval required before applying edits
- **Auto-Retry**: Up to 3 automatic retry attempts for test failures
- **Line-by-Line Edits**: Precise code modifications with validation
- **Parallel Evaluation**: Response quality assessment
- **Smart Caching**: Similarity-based deduplication

## Architecture
```
graph: intent → [read|edit|run|undo|profile] → evaluator → END
edit flow: edit → approve → apply → test → (retry if needed)
```

## Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export DEEPSEEK_API_KEY="your-key-here"

# Run agent
python main.py
```

## Usage
```
You> run tests
You> fix them
[Shows edit plan]
You> approve
[Applies edits, runs tests, auto-retries if needed]
```

## Project Structure
```
agent-v1/
├── main.py              # Entry point
├── graph.py             # LangGraph definition
├── core/
│   ├── state.py         # Agent state
│   └── memory.py        # Memory management
├── nodes/               # Graph nodes
│   ├── intent.py
│   ├── edit.py
│   ├── approve.py
│   ├── apply.py
│   ├── test.py
│   ├── read.py
│   ├── run.py
│   ├── undo.py
│   ├── profile.py
│   └── evaluator.py
├── mcp/                 # MCP servers
│   ├── client.py
│   ├── filesystem_server.py
│   └── execution_server.py
└── tools/               # Tool adapters
    └── mcp_adapter.py
```

## Key Components

### MCP Integration
- **Client**: Manages subprocess connections to MCP servers
- **Servers**: Python-based JSON-RPC servers for filesystem and execution
- **Adapter**: Routes calls through MCP with fallback to direct implementation

### Edit Flow
1. **Edit Node**: Generates line-by-line edit plan with numbered context
2. **Approve Node**: Presents edits for user approval
3. **Apply Node**: Applies approved edits with validation
4. **Test Node**: Runs tests and triggers retry if needed

### Memory System
- **Session**: Current files and conversation (last 10)
- **Persistent**: Cached responses with similarity deduplication
- **Smart Caching**: Updates similar queries instead of creating duplicates

## Testing
Tested with sample Flask Task Manager API project.
