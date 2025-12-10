# MCP Integration

## Overview

The agent uses **real MCP (Model Context Protocol)** to communicate with external tool servers.

## Architecture

```
Agent
  ↓
MCP Adapter (tools/mcp_adapter.py)
  ↓
MCP Client (mcp/client.py)
  ↓
┌─────────────────┬─────────────────┐
│ Filesystem MCP  │  Execution MCP  │
│ (Node.js/npx)   │  (Python)       │
└─────────────────┴─────────────────┘
  ↓                 ↓
JSON-RPC 2.0      JSON-RPC 2.0
```

## MCP Servers

### 1. Filesystem Server

- **Source**: `@modelcontextprotocol/server-filesystem` (community)
- **Command**: `npx -y @modelcontextprotocol/server-filesystem <project-dir>`
- **Tools**:
  - `list_directory`: List files
  - `read_file`: Read file content
  - `write_file`: Write file content

### 2. Execution Server

- **Source**: `mcp/execution_server.py` (custom)
- **Command**: `python3 mcp/execution_server.py`
- **Tools**:
  - `execute_command`: Run shell commands with timeout

## Protocol Flow

### 1. Server Startup

```python
# Start server process
process = subprocess.Popen(command, stdin=PIPE, stdout=PIPE)

# Send initialize request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {}
  }
}

# Receive response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "...", "version": "..."}
  }
}
```

### 2. Tool Discovery

```python
# Request tools list
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}

# Receive tools
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read file content",
        "inputSchema": {...}
      }
    ]
  }
}
```

### 3. Tool Call

```python
# Call tool
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {"path": "main.py"}
  }
}

# Receive result
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {"type": "text", "text": "file content here"}
    ]
  }
}
```

## Fallback Strategy

The MCP Adapter implements automatic fallback:

```python
async def read_file(filepath: str) -> str:
    # Try MCP first
    if mcp_available:
        try:
            result = await mcp_client.call_tool("filesystem", "read_file", {...})
            if result:
                return result
        except:
            pass
    
    # Fallback to direct
    return direct_read_file(filepath)
```

**Benefits**:
- Agent works even without MCP servers
- Graceful degradation
- No user intervention needed

## Adding New MCP Servers

1. **Create server** (or use community server)
2. **Add to `mcp/client.py`**:

```python
await mcp_client.add_server(
    "my-server",
    ["command", "to", "start", "server"]
)
```

3. **Update `mcp_adapter.py`** to use new tools

## Testing MCP Integration

```bash
# Run agent
python main.py

# Check startup output
Initializing MCP servers...
✓ MCP server 'filesystem' started with 3 tools
✓ MCP server 'execution' started with 1 tools
MCP Adapter: Connected to 2 servers with tools: {...}
```

## Troubleshooting

**Filesystem server fails**:
- Install Node.js: `brew install node`
- Or agent will use direct fallback

**Execution server fails**:
- Check Python 3 is available
- Check `mcp/execution_server.py` is executable
- Or agent will use direct fallback

**No MCP servers start**:
- Agent still works with direct tools
- All functionality preserved

## Why MCP?

1. **Extensibility**: Add new tools without changing agent code
2. **Separation**: Tools run in separate processes
3. **Reusability**: Same MCP servers work with any MCP client
4. **Community**: Use existing MCP servers from ecosystem
5. **Safety**: Sandboxed execution in separate processes

