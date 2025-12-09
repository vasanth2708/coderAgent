# Design Writeup: AI Coding Agent

## Overview

This document explains the design decisions and architecture of the AI Coding Agent, a LangGraph-based system that helps developers read, understand, and modify codebases through natural language interactions.

## 1. State Graph Design

### Graph Structure

```
START
  ↓
route (intent classification)
  ↓
  ├─→ profile → END
  ├─→ plan_read → read → END
  ├─→ edit → END
  ├─→ run_command → END
  └─→ undo → END
```

### Nodes and Transitions

**Route Node**: Entry point that classifies user intent using LLM-based classification. Routes to appropriate trajectory based on intent.

**Profile Node**: Handles user preference management. Stores preferences in persistent memory.

**Plan Read Node**: Uses LLM to select which files to read based on user query and session context.

**Read Node**: Retrieves file contents (from cache or disk), answers questions using LLM arbitration.

**Edit Node**: Plans edits using LLM, generates structured edit plans, stores in `pending_edits` for approval.

**Run Command Node**: Parses user command, executes it, captures output, and provides feedback.

**Undo Node**: Restores files from edit history backups, removes last edit from history.

### Decision Making

The agent uses a two-stage decision process:

1. **Intent Classification** (Route Node): LLM analyzes user text to determine intent
2. **Conditional Routing**: LangGraph routes based on `state.intent` value

This separation allows for:
- Easy addition of new intents
- Clear separation of concerns
- Testable routing logic

## 2. Edit Flow: "Add input validation to the create task endpoint"

### Sequence of Operations

1. **Route Node**: Classifies "add input validation" as `edit` intent

2. **Edit Node**:
   - Checks session context for file contents
   - If no files in context, calls `read_node` to load files
   - Uses LLM to identify relevant files (searches for "create task endpoint")
   - Reads fresh content from disk (ensures latest code)
   - Generates edit plan with line numbers
   - Stores plan in `state.pending_edits`

3. **User Approval**: User types "approve"

4. **Apply Edits** (`main.py::apply_pending_edits`):
   - Saves backups of files before editing (for undo)
   - Applies edits using `apply_line_edits()`
   - Updates session context with new content
   - Records edit in `edit_history`

5. **Test Execution**:
   - Runs `pytest` automatically
   - If tests fail, enters auto-fix loop

6. **Auto-Fix Loop** (if needed):
   - Refreshes file contents
   - Includes test errors in prompt
   - Generates new edits
   - Applies and re-tests
   - Max 3 attempts

### Tool Calls Sequence

```
1. list_python_files() - Get available files
2. read_file("routes/tasks.py") - Read target file
3. LLM call - Generate edit plan
4. apply_line_edits("routes/tasks.py", edits) - Apply changes
5. run_command(["pytest"]) - Verify changes
6. (If fail) LLM call - Generate fix
7. apply_line_edits() - Apply fix
8. run_command(["pytest"]) - Re-verify
```

## 3. Failure Handling: Edit Breaks Tests

### Scenario Flow

1. **Edit Applied**: Edits are applied to file, backups saved

2. **Test Execution**: `run_command(["pytest"])` returns non-zero exit code

3. **Auto-Fix Loop Triggered**:
   - Agent enters `auto_fix_loop()` in `main.py`
   - Max 3 fix attempts

4. **Each Fix Attempt**:
   - Refreshes file contents from disk
   - Includes previous test errors in prompt
   - Tracks attempt number in feedback history
   - Generates new edit plan
   - Applies edits
   - Re-runs tests

5. **Success Path**: Tests pass → Exit loop, notify user

6. **Failure Path** (after 3 attempts):
   - Agent stops trying
   - Notifies user that manual review needed
   - All edit history preserved for undo

### Error Recovery Mechanisms

- **Node-Level**: `@with_error_handling()` decorator catches exceptions, retries up to 3 times
- **Edit-Level**: Failed edits logged in `feedback_history`, inform next attempt
- **Test-Level**: Auto-fix loop with increasing context about failures
- **Safety**: Max retry limits prevent infinite loops

### What Happens Next

If auto-fix fails:
- User can manually review the code
- User can say "undo" to revert all changes
- User can provide more specific instructions
- Edit history is preserved for rollback

## 4. Memory Trade-offs: What to Keep vs. Discard

### Three-Tier Memory System

**Working Memory** (Current Task):
- **Keep**: Current node, step, retry count, recent errors
- **Discard**: Cleared on task completion
- **Rationale**: Only needed for current operation

**Session Memory** (Current Conversation):
- **Keep**: 
  - Files read in session (for context)
  - File contents (cached to avoid re-reading)
  - Last 10 conversation Q&A pairs
- **Discard**: 
  - Old conversation history (beyond 10 items)
  - Files not accessed recently
- **Rationale**: Balance between context and memory usage

**Persistent Memory** (Across Sessions):
- **Keep**:
  - User preferences (indefinitely)
  - Query cache (until code changes)
  - Execution logs (last 1000 entries)
- **Discard**:
  - Stale cache entries (when code hash changes)
  - Old execution logs (beyond 1000)
- **Rationale**: Preferences are permanent, cache is code-dependent

### Context Length Management

**When Context Gets Too Long**:

1. **Conversation History**: Keep last 10 items, truncate older ones
2. **File Contents**: Truncate to 50,000 characters (keeps beginning)
3. **LLM Prompts**: Truncate before sending to API
4. **Cache**: Evict oldest entries when limit reached (500 entries)

**Trade-offs**:
- **Truncation Strategy**: Currently keeps beginning, loses end. Could be improved with semantic chunking.
- **Cache Size**: 500 entries balances speed vs. memory
- **History Length**: 10 items provides context without overflow

### Decision Logic

**What Goes Where**:
- **Working**: Temporary, task-specific state
- **Session**: Current conversation context, file caches
- **Persistent**: User preferences, code-aware cache, historical logs

**Eviction Strategy**:
- **LRU for cache**: Oldest entries removed first
- **FIFO for history**: Oldest conversations dropped
- **Code-aware**: Cache invalidated when code hash changes

## 5. Adding 10 More Tools Without Changing Core Logic

### Current Architecture

Tools are abstracted through MCP modules (`mcps/` directory):
- `filesystem_mcp.py`: File operations
- `execution_mcp.py`: Command execution
- `edit_mcp.py`: Edit planning
- `read_mcp.py`: Context retrieval

### Extension Strategy

**1. Create New MCP Module**:
```python
# mcps/new_tool_mcp.py
def new_tool_function(state: AgentState, params):
    # Tool implementation
    return result
```

**2. Import in Graph/Node**:
```python
from mcps.new_tool_mcp import new_tool_function
```

**3. Use in Node**:
```python
@with_error_handling("new_node")
async def new_node(state: AgentState) -> AgentState:
    result = new_tool_function(state, params)
    # Process result
    return state
```

**4. Register in Graph** (if new trajectory):
```python
graph.add_node("new_node", new_node)
graph.add_conditional_edges("route", lambda s: s.intent, {
    # ... existing
    "new_intent": "new_node",
})
```

### Key Design Principles

1. **Separation of Concerns**: Tools are separate from orchestration
2. **Error Handling**: All tools wrapped with error handling
3. **State Management**: Tools receive and return state
4. **Extensibility**: New tools don't require graph changes (unless new trajectory)

### Example: Adding a Linter Tool

```python
# mcps/linter_mcp.py
def run_linter(filepath: str) -> dict:
    result = run_command(["ruff", "check", filepath])
    return {"errors": parse_errors(result), "file": filepath}

# In edit_node:
if preferences.get("auto_lint"):
    linter_result = run_linter(filepath)
    if linter_result["errors"]:
        # Include in edit prompt
```

**No core logic changes needed** - just add the tool and use it in nodes.

## Design Decisions Summary

### Why LangGraph?
- Clear state machine visualization
- Built-in error handling and retry mechanisms
- Easy to extend with new nodes
- Conditional routing support

### Why Three-Tier Memory?
- **Working**: Fast access to current task state
- **Session**: Efficient context management
- **Persistent**: Long-term learning and preferences

### Why LLM-Based Intent Classification?
- Handles natural language variations
- Can be improved with examples
- Flexible for new intents

### Why Edit Approval?
- Safety: Prevents accidental changes
- Transparency: User sees what will change
- Control: User can modify before applying

### Why Auto-Fix Loop?
- Reduces manual intervention
- Learns from failures
- Prevents infinite loops with max attempts

## Future Improvements

1. **Better Context Management**: Semantic chunking instead of simple truncation
2. **MCP Protocol Integration**: Full MCP server integration for tool discovery
3. **Streaming Output**: Real-time feedback as agent works
4. **Observability**: Detailed traces of tool calls and decisions
5. **Dry-Run Mode**: Preview changes without applying
6. **Multi-File Rollback**: Undo entire edit operations across files

## Conclusion

The architecture prioritizes:
- **Clarity**: Clear separation of concerns
- **Extensibility**: Easy to add new tools and trajectories
- **Safety**: Error handling, approval workflow, undo capability
- **Efficiency**: Caching, parallel operations, context management

The design balances functionality with maintainability, making it easy to extend while keeping the core logic clean and testable.

