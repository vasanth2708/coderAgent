# AI Coding Agent

Production-ready LangGraph-based coding agent with real MCP integration and intelligent auto-fix capabilities.

## Quick Start

```bash
# Setup
cd agent-v1
pip install -r requirements.txt
export DEEPSEEK_API_KEY="your-key"

# Run
python main.py
```

## Features

- **Real MCP Protocol**: JSON-RPC based filesystem and execution servers
- **Smart Editing**: Line-by-line edits with approval flow
- **Auto-Fix Loop**: Up to 3 automatic retry attempts for test failures
- **Intelligent Caching**: Similarity-based deduplication (70% threshold)
- **Parallel Evaluation**: Response quality scoring (1-5 scale)

## Architecture

```
Intent → [Read|Edit|Run|Undo|Profile] → Evaluator → END
Edit Flow: Edit → Approve → Apply → Test → Retry (if needed)
```

## Sample Project

Includes Flask Task Manager API for testing:
- 5 test cases
- CRUD operations
- Validation testing

## Documentation

See `agent-v1/README.md` for detailed documentation.
