# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Main Loop                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  User Input → Graph Execution → Response Output      │   │
│  │       ↓              ↓                ↓               │   │
│  │   State Mgmt    Node Execution   Evaluation          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. LangGraph Flow

```
                    ┌──────────┐
                    │  START   │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │  Intent  │
                    └────┬─────┘
                         │
        ┌────────────────┼────────────────┬────────────┐
        │                │                │            │
   ┌────▼────┐     ┌────▼────┐     ┌────▼────┐  ┌────▼────┐
   │  Read   │     │  Edit   │     │   Run   │  │  Undo   │
   └────┬────┘     └────┬────┘     └────┬────┘  └────┬────┘
        │               │                │            │
        │          ┌────▼─────┐          │            │
        │          │ Approve  │          │            │
        │          └────┬─────┘          │            │
        │               │                │            │
        │          ┌────▼─────┐          │            │
        │          │  Apply   │          │            │
        │          └────┬─────┘          │            │
        │               │                │            │
        │          ┌────▼─────┐          │            │
        │          │Run(Tests)│◄─────────┘            │
        │          └────┬─────┘                       │
        │               │                             │
        │          ┌────▼─────┐                       │
        │          │  Retry?  │                       │
        │          └────┬─────┘                       │
        │               │                             │
        └───────────────┼─────────────────────────────┘
                        │
                   ┌────▼──────┐
                   │ Evaluator │
                   └────┬──────┘
                        │
                   ┌────▼────┐
                   │   END   │
                   └─────────┘
```

### 2. MCP Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Process                         │
│  ┌────────────┐         ┌──────────────┐               │
│  │ MCP Client │◄────────┤ MCP Adapter  │               │
│  └─────┬──────┘         └──────────────┘               │
│        │                                                 │
│        │ JSON-RPC over stdin/stdout                     │
│        │                                                 │
│  ┌─────▼──────────────────────────────────┐            │
│  │        Subprocess Management            │            │
│  └─────┬───────────────────┬──────────────┘            │
└────────┼───────────────────┼─────────────────────────────┘
         │                   │
    ┌────▼────┐         ┌────▼────┐
    │ FS      │         │ Exec    │
    │ Server  │         │ Server  │
    └─────────┘         └─────────┘
```

### 3. State Management

```
┌─────────────────────────────────────────┐
│           AgentState                     │
├─────────────────────────────────────────┤
│ messages: List[BaseMessage]             │
│ intent: str                              │
│ target_files: List[str]                 │
│ pending_edits: Dict                     │
│ awaiting_approval: bool                 │
│ retry_count: int                        │
│ last_test_result: Dict                  │
│ memory: Memory                          │
│ edit_history: List[Dict]                │
└─────────────────────────────────────────┘
```

### 4. Memory System

```
┌────────────────────────────────────────────┐
│              Memory                         │
├────────────────────────────────────────────┤
│  Session (Ephemeral)                       │
│  ├─ files: Dict[str, str]                  │
│  ├─ conversation: List[Dict] (last 10)     │
│  ├─ accessed: Set[str]                     │
│  └─ edit_history: List[Dict]               │
│      └─ {file, backup, timestamp}          │
│                                             │
│  Persistent (Disk)                         │
│  ├─ cache: Dict[hash, response]            │
│  │   └─ Similarity deduplication (70%)     │
│  ├─ file_hashes: Dict[path, hash]          │
│  └─ recent_conversations: List (last 20)   │
└────────────────────────────────────────────┘
```

## Data Flow

### Edit Flow with Retry

```
1. User: "fix them"
   ↓
2. Intent Node → intent="edit"
   ↓
3. Edit Node
   ├─ Parse test errors from messages
   ├─ Select target file (tests/test_tasks.py)
   ├─ Read file with line numbers
   ├─ Generate line-by-line edits
   │  └─ {"line": 85, "old": "json(x)", "new": "json.dumps(x)"}
   └─ Set pending_edits
   ↓
4. Approve Node
   ├─ Display edit plan
   ├─ Set awaiting_approval=True
   └─ Pause (return to main)
   ↓
5. User: "approve"
   ↓
6. Apply Node
   ├─ Backup file to edit_history
   ├─ Apply edits in reverse order
   ├─ Validate each line
   ├─ Write file
   └─ Set _run_tests_after_apply flag
   ↓
7. Run Node (Test Mode)
   ├─ Detect _run_tests_after_apply flag
   ├─ Run pytest
   ├─ Check success
   └─ If failed:
       ├─ retry_count++
       ├─ Add error to messages
       ├─ Clear pending_edits
       └─ Route back to Intent (→ Edit)
   ↓
8. Evaluator Node (parallel)
   ├─ Score response (1-5)
   ├─ Log evaluation
   └─ Continue to END
```

### Undo Flow

```
1. User: "undo"
   ↓
2. Intent Node → intent="undo"
   ↓
3. Undo Node
   ├─ Check edit_history
   ├─ Pop last edit
   │  └─ {file: "path", backup: "content", timestamp: "..."}
   ├─ Restore file from backup
   ├─ Update memory with backup content
   └─ Confirm to user
   ↓
4. Evaluator Node
   ├─ Score response
   └─ Continue to END
```

### Run Flow (Command Execution)

```
1. User: "run tests" or "run main.py"
   ↓
2. Intent Node → intent="run"
   ↓
3. Run Node (Command Mode)
   ├─ Parse user command
   │  ├─ "run tests" → ["pytest", "-xvs"]
   │  ├─ "run main" → ["python3", "main.py"]
   │  └─ Complex queries → Use LLM to parse
   ├─ Execute command via MCP
   ├─ Capture stdout/stderr
   └─ Format output
   ↓
4. Evaluator Node
   ├─ Score response
   └─ Continue to END
```

### Cache Flow with Deduplication

```
1. Query arrives: "explain complete code"
   ↓
2. Compute code_hash from files
   ↓
3. Check cache:
   ├─ Exact match? → Return cached
   └─ No match → Continue
   ↓
4. Check similarity (70% word overlap)
   ├─ Similar query found?
   │  └─ Update existing entry
   └─ No similar query
      └─ Create new entry
   ↓
5. Generate response via LLM
   ↓
6. Cache response with deduplication
```

### Complete Edit-Test-Undo Workflow

```
1. User: "fix the bug"
   ↓
2. Edit → Approve → User: "yes"
   ↓
3. Apply Node
   ├─ Backup: edit_history.push({
   │    file: "test.py",
   │    backup: "original content...",
   │    timestamp: "2024-01-01 10:00:00"
   │  })
   ├─ Apply edits
   └─ Set _run_tests_after_apply = True
   ↓
4. Run Node (Test Mode)
   ├─ Run pytest
   └─ Tests PASS ✓
   ↓
5. User: "actually, undo that"
   ↓
6. Undo Node
   ├─ Pop from edit_history
   ├─ Restore original content
   └─ Confirm: "Reverted changes to test.py"
   ↓
7. File is back to original state
```

## Routing Logic

### Intent-Based Routing
```python
route_intent(state):
    intent_map = {
        "read": "read",
        "edit": "edit", 
        "run": "run",
        "undo": "undo",
        "profile": "profile"
    }
    return intent_map.get(state.intent, "read")
```

### Edit Flow Routing
```python
route_after_edit(state):
    if state.pending_edits:
        return "approve"  # User must approve edits
    return END

route_after_apply(state):
    return "run"  # Always test after applying edits
```

### Run Node Routing (Context-Aware)
```python
route_run(state):
    if hasattr(state, '_run_tests_after_apply') and not state.done:
        return "intent"  # Tests failed, retry edit
    elif state.done:
        return "evaluator"  # Success or normal command
    else:
        return "evaluator"  # Default
```

### Terminal Nodes
```python
# These nodes always go to evaluator before END
for node in ["read", "undo", "profile"]:
    graph.add_edge(node, "evaluator")

# Evaluator always terminates
graph.add_edge("evaluator", END)
```

## Node Responsibilities

### Intent Node
- Classify user intent using LLM
- Set `state.intent` for routing
- Handle context from previous messages
- Supported intents: read, edit, run, undo, profile

### Read Node
- Read and display file contents
- Support for multiple files
- Add files to memory for context
- Format output with syntax awareness

### Edit Node
- Parse test errors for file detection
- Add line numbers to code context
- Generate precise line-by-line edits
- Format: `{"line": N, "old": "...", "new": "..."}`
- Set pending_edits for approval

### Approve Node
- Present edit plan to user
- Set `awaiting_approval=True`
- Pause graph execution
- Wait for user approval/rejection

### Apply Node
- Backup files to edit_history before editing
- Apply edits in reverse order (maintain line numbers)
- Validate old code matches current line
- Update memory with new content
- Set `_run_tests_after_apply` flag for testing

### Run Node (Dual Mode)
**Command Mode** (default):
- Parse user command intelligently
- Support common patterns (pytest, python, lint)
- Use LLM for complex command parsing
- Execute via MCP and capture output

**Test Mode** (after apply):
- Detect `_run_tests_after_apply` flag
- Execute pytest with retry logic
- Handle test failures:
  - Increment `retry_count`
  - Add error context to messages
  - Route back to edit if retries remain
  - Stop at max_retries (3)

### Undo Node
- Check edit_history for previous edits
- Pop last edit from history stack
- Restore file from backup content
- Update memory with restored content
- Confirm revert to user

### Profile Node
- Display agent capabilities
- Show available commands
- Provide usage examples
- Help and documentation

### Evaluator Node
- Score response quality (1-5)
- Log to `.evaluation_log.json`
- Run after output nodes
- Non-blocking (errors don't fail main flow)

## Key Design Decisions

### 1. Line-by-Line Edits
**Why**: Precise, validatable, maintains file structure
**Format**: `{"line": 85, "old": "current", "new": "replacement"}`
**Benefits**:
- Easy to validate
- Clear to user
- Minimal risk of corruption
- Supports undo via backup

### 2. Approval Flow in Graph
**Why**: Separation of concerns, testable
**Implementation**: 
- Approve node sets `awaiting_approval=True`
- Main loop handles user input
- Apply/Run nodes continue execution
**Benefits**:
- Clean graph structure
- Reusable approval logic
- Easy to extend

### 3. Unified Run Node (Command + Test)
**Why**: Consolidate execution logic, reduce complexity
**Implementation**:
- Single node handles both command execution and testing
- Flag-based mode switching (`_run_tests_after_apply`)
- Test mode includes retry logic
**Benefits**:
- Simpler graph structure
- Reduced code duplication
- Consistent execution interface
- Easier to maintain

### 4. Edit History with Undo
**Why**: Safety net for code changes
**Implementation**:
- Stack-based edit history
- Each edit stores: file path, backup content, timestamp
- Undo pops last edit and restores backup
**Benefits**:
- Safe experimentation
- Quick recovery from mistakes
- No external version control needed
- User confidence in making changes

### 5. Retry Logic in Run Node (Test Mode)
**Why**: Automatic recovery from test failures
**Implementation**:
- Run node checks `retry_count` when in test mode
- Adds error context to messages
- Routes back to Intent → Edit
**Benefits**:
- Self-healing
- Context accumulation
- Bounded retries (max 3)

### 6. Similarity-Based Cache Deduplication
**Why**: Prevent redundant cached entries
**Implementation**:
- 70% word overlap threshold
- Updates existing entry instead of creating new
- Same logic for reads and writes
**Benefits**:
- Reduced cache bloat
- Consistent responses
- Better cache utilization

### 7. MCP with Fallback
**Why**: Real protocol with safety net
**Implementation**:
- Try MCP first
- Fall back to direct on failure
- Log which path was used
**Benefits**:
- Production-ready
- Debuggable
- Resilient

## Performance Characteristics

### Scalability Limits
- Max file size: ~100KB (LLM context limit)
- Max edits per file: 30 (safety limit)
- Max retry attempts: 3
- Max cache entries: 500
- Edit history: Unlimited (memory-based stack)

## Security Considerations

1. **Sandbox Execution**: MCP servers run in subprocess
2. **Input Validation**: File paths validated before access
3. **Sensitive Data Filtering**: API keys/passwords not cached
4. **Backup Before Edit**: All edits backed up in history stack
5. **Bounded Retries**: Prevents infinite loops (max 3 attempts)
6. **Undo Safety**: Restores exact backup content, no partial restores
7. **Command Validation**: User commands parsed and validated before execution

## Extension Points

1. **New Intents**: Add node + routing in graph.py
2. **New Tools**: Add MCP server or direct implementation
3. **Custom Evaluation**: Modify evaluator_node.py
4. **Cache Strategy**: Modify memory.py deduplication logic
5. **Retry Strategy**: Adjust max_retries in state.py
6. **Undo Enhancements**: 
   - Add selective undo (undo specific file)
   - Add redo functionality
   - Persist edit history to disk
7. **Run Node Extensions**:
   - Add more command patterns
   - Support custom test frameworks
   - Add pre/post execution hooks

