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
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼────┐     ┌────▼────┐     ┌────▼────┐
   │  Read   │     │  Edit   │     │   Run   │
   └────┬────┘     └────┬────┘     └────┬────┘
        │               │                │
        │          ┌────▼─────┐          │
        │          │ Approve  │          │
        │          └────┬─────┘          │
        │               │                │
        │          ┌────▼─────┐          │
        │          │  Apply   │          │
        │          └────┬─────┘          │
        │               │                │
        │          ┌────▼─────┐          │
        │          │   Test   │          │
        │          └────┬─────┘          │
        │               │                │
        │          ┌────▼─────┐          │
        │          │  Retry?  │          │
        │          └────┬─────┘          │
        │               │                │
        └───────────────┼────────────────┘
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
│  └─ accessed: Set[str]                     │
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
   ├─ Backup file
   ├─ Apply edits in reverse order
   ├─ Validate each line
   └─ Write file
   ↓
7. Test Node
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

## Node Responsibilities

### Intent Node
- Classify user intent using LLM
- Set `state.intent` for routing
- Handle context from previous messages

### Edit Node
- Parse test errors for file detection
- Add line numbers to code context
- Generate precise line-by-line edits
- Format: `{"line": N, "old": "...", "new": "..."}`

### Approve Node
- Present edit plan to user
- Set `awaiting_approval=True`
- Pause graph execution

### Apply Node
- Backup files before editing
- Apply edits in reverse order (maintain line numbers)
- Validate old code matches
- Update memory with new content

### Test Node
- Execute pytest
- Check results
- Handle retry logic:
  - Increment `retry_count`
  - Add error context to messages
  - Route back to edit if retries remain
  - Stop at max_retries (3)

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

### 2. Approval Flow in Graph
**Why**: Separation of concerns, testable
**Implementation**: 
- Approve node sets `awaiting_approval=True`
- Main loop handles user input
- Apply/Test nodes continue execution
**Benefits**:
- Clean graph structure
- Reusable approval logic
- Easy to extend

### 3. Retry Logic in Test Node
**Why**: Automatic recovery from failures
**Implementation**:
- Test node checks `retry_count`
- Adds error context to messages
- Routes back to Intent → Edit
**Benefits**:
- Self-healing
- Context accumulation
- Bounded retries (max 3)

### 4. Similarity-Based Cache Deduplication
**Why**: Prevent redundant cached entries
**Implementation**:
- 70% word overlap threshold
- Updates existing entry instead of creating new
- Same logic for reads and writes
**Benefits**:
- Reduced cache bloat
- Consistent responses
- Better cache utilization

### 5. MCP with Fallback
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

## Security Considerations

1. **Sandbox Execution**: MCP servers run in subprocess
2. **Input Validation**: File paths validated before access
3. **Sensitive Data Filtering**: API keys/passwords not cached
4. **Backup Before Edit**: All edits backed up in history
5. **Bounded Retries**: Prevents infinite loops

## Extension Points

1. **New Intents**: Add node + routing in graph.py
2. **New Tools**: Add MCP server or direct implementation
3. **Custom Evaluation**: Modify evaluator_node.py
4. **Cache Strategy**: Modify memory.py deduplication logic
5. **Retry Strategy**: Adjust max_retries in state.py

