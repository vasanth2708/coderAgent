# Agent Architecture Documentation

## 1. Orchestrator Design

### LangGraph State Machine

The agent uses **LangGraph** to implement a clear state machine with the following structure:

```
START → route → [intent-based routing]
                ├─→ profile → END
                ├─→ plan_read → read → END
                ├─→ edit → END
                └─→ run_command → END
```

### State Machine Components

- **Route Node**: Classifies user intent (read, edit, run_command, profile)
- **Profile Node**: Handles user preference updates
- **Plan Read Node**: Selects which files to read
- **Read Node**: Retrieves and caches file contents, answers questions
- **Edit Node**: Plans and generates code edits
- **Run Command Node**: Executes shell commands

### Decision Making

The agent decides which trajectory to take through:
1. **Intent Classification**: LLM-based classification in `route_node`
2. **Conditional Edges**: LangGraph conditional routing based on `state.intent`
3. **Context Awareness**: Uses session context and memory to inform decisions

### Error Handling

All nodes are wrapped with `@with_error_handling()` decorator that:
- Catches exceptions during node execution
- Tracks retry attempts in `working_memory.retry_count`
- Prevents infinite loops (max 3 retries per node)
- Logs errors to `working_memory.feedback_history`
- Returns graceful error messages to user

**Recovery Strategy**:
- Errors are caught and logged
- State is preserved with error context
- User receives informative error message
- Agent can retry with updated context

### Adding New Trajectories

To add a new trajectory:

1. **Add intent to state** (`state.py`):
   ```python
   intent: Optional[Literal["read", "edit", "run_command", "profile", "new_intent"]]
   ```

2. **Update intent classification** (`mcps/intent_mcp.py`):
   - Add pattern matching or LLM prompt update

3. **Create node function** (`graph.py`):
   ```python
   @with_error_handling("new_node")
   async def new_node(state: AgentState) -> AgentState:
       state.working_memory["current_step"] = "doing_work"
       # Your logic here
       return state
   ```

4. **Register in graph** (`graph.py`):
   ```python
   graph.add_node("new_node", new_node)
   graph.add_conditional_edges("route", lambda s: s.intent, {
       # ... existing intents
       "new_intent": "new_node",
   })
   graph.add_edge("new_node", END)
   ```

## 2. Memory Architecture

### Three-Tier Memory System

#### Working Memory (Current Task)
**Location**: `state.working_memory`
**Scope**: Current task only
**Contents**:
- `current_node`: Which node is executing
- `current_step`: Current step within node
- `current_file`: File being processed
- `retry_count`: Number of retry attempts
- `last_error`: Last error encountered
- `feedback_history`: Recent feedback from tool executions

**Lifecycle**: Reset between tasks, cleared on success

#### Session Memory (Current Conversation)
**Location**: `state.session_context`
**Scope**: Current session (until agent restarts)
**Contents**:
- `read_files`: List of files read in this session
- `file_contents`: Cached file contents (keyed by filepath)
- `conversation_history`: Recent Q&A pairs (max 10 items, truncated)

**Lifecycle**: Persists across requests in same session, cleared on restart

#### Persistent Memory (Across Sessions)
**Location**: `state.memory` (loaded from `.coder_agent_memory.json`)
**Scope**: Persists across all sessions
**Contents**:
- `preferences`: User preferences (e.g., "always add docstrings")
- `query_cache`: Cached responses keyed by code hash + query
- `node_log`: Execution logs for all nodes (max 1000 entries)
- `memory_log`: General memory events

**Lifecycle**: Saved to disk, loaded on startup

### Memory Decision Logic

**What goes where?**

- **Working Memory**: 
  - Current task state
  - Temporary error context
  - In-progress operation details

- **Session Memory**:
  - Files read/edited in current session
  - Conversation history
  - Temporary file caches

- **Persistent Memory**:
  - User preferences
  - Code-aware query cache (invalidated on code changes)
  - Historical execution logs

### Context Length Management

**Automatic Truncation**:
- `truncate_context()`: Truncates content to `MAX_CONTEXT_LENGTH` (50,000 chars)
- `manage_conversation_history()`: Limits conversation history to 10 items
- File contents are truncated when building LLM prompts
- Query/response pairs in cache are truncated

**When Context Gets Too Long**:
1. Conversation history is trimmed (keeps most recent)
2. File contents are truncated (keeps beginning)
3. LLM prompts are truncated before sending
4. Cache entries are evicted (LRU-style, oldest first)

## 3. Feedback Integration

### Self-Correction Mechanisms

#### 1. Tool Output Feedback

**Command Execution**:
- Exit codes are captured and stored in `feedback_history`
- Failed commands add error context to subsequent attempts
- Success/failure influences next command selection

**Edit Application**:
- Edit success/failure is tracked
- Failed edits are logged with error details
- Previous failures are included in next edit attempt context

#### 2. Auto-Fix Loop

**Location**: `main.py::auto_fix_loop()`

**Process**:
1. Tests fail after edits
2. Agent enters auto-fix loop (max 3 attempts)
3. Each attempt:
   - Refreshes file contents from disk
   - Includes previous failure context
   - Generates new edits
   - Applies edits
   - Re-runs tests
4. Loop exits on success or max attempts

**Feedback Integration**:
- Previous test failures are included in fix prompts
- Number of failed attempts is tracked
- Different approaches are suggested after repeated failures

#### 3. Retry Prevention

**Infinite Loop Prevention**:
- `retry_count` tracked in `working_memory`
- Max 3 retries per node execution
- Max 3 auto-fix attempts
- Safety check: breaks if retry_count > max_attempts * 2

**Feedback History**:
- Last 20 feedback entries kept
- Includes: command executions, edit failures, errors
- Used to inform subsequent decisions

### How Corrections Influence Behavior

1. **Error Context**: Previous errors are included in prompts
2. **Retry Tracking**: Agent knows how many times it's tried
3. **Feedback History**: Recent failures inform next approach
4. **Different Strategies**: After repeated failures, agent tries different approaches

### Example Feedback Flow

```
User: "Fix the bug"
→ Edit node generates edits
→ Edits applied
→ Tests run (FAIL)
→ Auto-fix loop:
  Attempt 1: Includes test errors, generates new edits
  Attempt 2: Includes attempt 1 failure, tries different approach
  Attempt 3: Includes both failures, suggests manual review
```

## Summary

- **Orchestrator**: LangGraph state machine with clear routing
- **Error Handling**: Wrapped nodes with retry limits and recovery
- **Memory**: Three-tier system (working/session/persistent)
- **Context Management**: Automatic truncation and history management
- **Feedback**: Self-correction with tool output analysis
- **Retry Prevention**: Max attempts with safety checks
- **Extensibility**: Clear pattern for adding new trajectories

