# Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                         │
│                    (CLI: main.py)                           │
└──────────────────────┬────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  LangGraph State Machine                     │
│                                                              │
│  START → route → [Intent Classification]                     │
│                    │                                         │
│        ┌───────────┼───────────┐                            │
│        │           │           │                            │
│        ▼           ▼           ▼                            │
│     profile    plan_read    edit    run_command   undo      │
│        │           │           │         │          │        │
│        │           ▼           │         │          │        │
│        │          read          │         │          │        │
│        │           │            │         │          │        │
│        └───────────┴────────────┴─────────┴──────────┘        │
│                            │                                 │
│                            ▼                                 │
│                           END                                │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent State                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Working Memory (Current Task)                      │    │
│  │ - current_node, current_step                       │    │
│  │ - retry_count, last_error                          │    │
│  │ - feedback_history                                 │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Session Memory (Current Conversation)              │    │
│  │ - read_files, file_contents                       │    │
│  │ - conversation_history (last 10)                  │    │
│  │ - edit_history (last 10)                          │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Persistent Memory (Across Sessions)                │    │
│  │ - preferences                                      │    │
│  │ - query_cache (code-aware)                         │    │
│  │ - node_log (execution history)                     │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   MCP Tools  │ │  LLM Service │ │  File System │
│              │ │              │ │              │
│ - filesystem │ │ - DeepSeek   │ │ - sampleProj │
│ - execution  │ │ - OpenAI     │ │ - .memory    │
│ - edit       │ │              │ │              │
│ - read       │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Trajectory Flows

### Read Trajectory
```
User: "What does X do?"
  ↓
route → plan_read → read → END
         │          │
         │          ├→ Retrieve files
         │          ├→ Check cache
         │          ├→ LLM arbitration
         │          └→ Return answer
         │
         └→ Select files to read
```

### Edit Trajectory
```
User: "Add validation to X"
  ↓
route → edit → END
         │
         ├→ Check session context
         ├→ Read files (if needed)
         ├→ Generate edit plan
         ├→ Store in pending_edits
         └→ Wait for approval
         
User: "approve"
  ↓
apply_pending_edits()
  ├→ Save backups
  ├→ Apply edits
  ├→ Run tests
  └→ Auto-fix loop (if tests fail)
```

### Run Command Trajectory
```
User: "Run tests"
  ↓
route → run_command → END
         │
         ├→ Parse command
         ├→ Execute (with timeout)
         ├→ Capture output
         ├→ Store in feedback_history
         └→ Return results
```

### Undo Trajectory
```
User: "undo" or "that's wrong"
  ↓
route → undo → END
         │
         ├→ Check edit_history
         ├→ Get last backup
         ├→ Restore files
         └→ Remove from history
```

## Memory Flow

```
┌─────────────────────────────────────────────────────────┐
│                    Memory Tiers                         │
└─────────────────────────────────────────────────────────┘

Working Memory (Ephemeral)
  │
  ├→ Created at task start
  ├→ Updated during execution
  └→ Cleared on completion

Session Memory (Per Session)
  │
  ├→ Persists across requests
  ├→ File caches
  ├→ Conversation history (truncated)
  └→ Edit history (for undo)

Persistent Memory (Disk)
  │
  ├→ .coder_agent_memory.json
  ├→ Preferences (permanent)
  ├→ Query cache (code-aware)
  └→ Execution logs (last 1000)
```

## Error Handling Flow

```
Node Execution
  │
  ├→ @with_error_handling wrapper
  │   │
  │   ├→ Try: Execute node
  │   │
  │   └→ Catch: Exception
  │       │
  │       ├→ Log error
  │       ├→ Increment retry_count
  │       ├→ Add to feedback_history
  │       │
  │       ├→ If retry_count > 3:
  │       │   └→ Return error, stop
  │       │
  │       └→ Else:
  │           └→ Retry with context
```

## Tool Integration Pattern

```
Node
  │
  ├→ Import tool function
  │   from mcps.filesystem_mcp import read_file
  │
  ├→ Call tool
  │   result = read_file(filepath)
  │
  ├→ Handle result
  │   if result["error"]:
  │       # Error handling
  │
  └→ Update state
      state.session_context["file_contents"][filepath] = result
```

## Feedback Integration

```
Tool Execution
  │
  ├→ Capture output
  │   exit_code, stdout, stderr
  │
  ├→ Store in feedback_history
  │   {
  │     "type": "command_execution",
  │     "success": exit_code == 0,
  │     "output": stdout
  │   }
  │
  ├→ If failure:
  │   ├→ Add to next prompt context
  │   └→ Inform auto-fix loop
  │
  └→ Influence next decision
      Use feedback_history in prompts
```

## Context Management

```
Content Too Long?
  │
  ├→ Conversation History
  │   └→ Keep last 10 items
  │
  ├→ File Contents
  │   └→ Truncate to 50,000 chars
  │
  ├→ LLM Prompts
  │   └→ Truncate before sending
  │
  └→ Cache
      └→ Evict oldest (LRU)
```

## Auto-Fix Loop

```
Tests Fail
  │
  ├→ Enter auto_fix_loop()
  │   max_attempts = 3
  │
  ├→ For each attempt:
  │   ├→ Refresh file contents
  │   ├→ Include test errors in prompt
  │   ├→ Generate new edits
  │   ├→ Apply edits
  │   ├→ Re-run tests
  │   │
  │   └→ If success: Exit loop
  │
  └→ If all attempts fail:
      └→ Notify user, preserve history
```

