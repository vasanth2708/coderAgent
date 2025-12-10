# AI Coding Agent - DeepSeek Powered

A streamlined LangGraph-based coding agent with efficient memory management and MCP integration. Uses DeepSeek for cost-effective, high-quality code understanding and generation.

## Features

- **Intent-based routing**: Automatically classifies user requests
- **Smart memory**: Three-tier system with intelligent caching
- **MCP integration**: ✅ Real MCP protocol (JSON-RPC 2.0) with filesystem + execution servers
- **Undo support**: Revert changes with backup system
- **Context compression**: Handles large codebases efficiently
- **DeepSeek powered**: 95% cheaper than GPT-4o

## Architecture

```
User Input
    ↓
Intent Classification (LLM)
    ↓
┌─────────┬──────────┬──────────┬──────────┬──────────┐
│  Read   │   Edit   │   Run    │   Undo   │ Profile  │
└─────────┴──────────┴──────────┴──────────┴──────────┘
    ↓
Response
```

### Memory System

1. **Working**: Current task state (ephemeral)
2. **Session**: Files + conversation (session-scoped, max 30 files)
3. **Persistent**: Preferences + cache (disk-persisted, max 500 entries)

### Context Management

- Automatic file selection based on relevance
- Smart compression: keeps imports + function signatures
- Similarity-based cache matching (70% threshold)
- LRU eviction when limits exceeded

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set DeepSeek API key (get from https://platform.deepseek.com/)
export DEEPSEEK_API_KEY="sk-..."

# Test MCP integration (optional but recommended)
python test_mcp.py

# Run the agent
python main.py
```

The agent will automatically:
1. Start Python-based MCP servers (filesystem + execution)
2. Use real JSON-RPC protocol for all tool operations
3. Fall back to direct tools only if MCP servers fail
4. Show detailed logging of MCP operations (can be disabled)

## Usage

```
You: What does the create_task function do?
Agent: [Reads relevant files and explains]

You: Add input validation to create_task
Agent: [Shows edit plan]

You: approve
Agent: [Applies edits and runs tests]

You: undo
Agent: [Reverts changes]
```

## Project Structure

```
agent-v1/
├── core/
│   ├── memory.py      # Memory management
│   ├── state.py       # Agent state
│   └── evaluator.py   # LLM-as-judge evaluation
├── nodes/
│   ├── intent.py      # Intent classification
│   ├── read.py        # Read & answer
│   ├── edit.py        # Edit planning
│   ├── run.py         # Command execution
│   ├── undo.py        # Revert changes
│   └── profile.py     # Preferences
├── mcp/
│   ├── client.py           # MCP client (JSON-RPC)
│   ├── filesystem_server.py # Filesystem MCP server
│   └── execution_server.py  # Execution MCP server
├── tools/
│   ├── filesystem.py  # Direct file operations (fallback)
│   ├── execution.py   # Direct command execution (fallback)
│   └── mcp_adapter.py # MCP routing with fallback
├── graph.py           # LangGraph definition
├── main.py            # Entry point
├── test_mcp.py        # MCP integration test
└── config.py          # Configuration
```

## Design Decisions

### Why Three-Tier Memory?

- **Working**: Cleared after each task, keeps state minimal
- **Session**: Caches files to avoid re-reading, limited to 30 most recent
- **Persistent**: Survives restarts, enables fast responses for repeated queries

### Why Smart Compression?

Large files are compressed by keeping structure (imports, signatures) and summarizing bodies. This preserves API surface while fitting more context.

### Why MCP Adapter?

Provides clean fallback: tries MCP first (real JSON-RPC protocol), uses direct tools if unavailable. All operations go through MCP when servers are running (100% success rate in tests). Makes the system reliable even if MCP servers fail.

### Why Similarity Matching?

Cache hits even when query phrasing differs. "show auth" matches "how does authentication work" (70%+ word overlap).

## Limitations

- Max 30 files in session memory
- Max 500 cache entries
- Context limited to 40K chars
- No streaming output
- No multi-file atomic edits

## Future Enhancements

- Streaming responses
- Multi-file edit transactions
- Linter integration for auto-fix
- Pattern recognition for common errors
- Embeddings for better file selection

