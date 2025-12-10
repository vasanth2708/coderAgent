# Architecture

## Flow

```
┌─────────────┐
│ User Input  │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Intent Node     │  LLM classifies: read/edit/run/undo/profile
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│ Route           │  Conditional routing based on intent
└──────┬──────────┘
       │
       ├──→ Read Node ──────→ Answer question
       ├──→ Edit Node ──────→ Plan edits
       ├──→ Run Node ───────→ Execute command
       ├──→ Undo Node ──────→ Revert changes
       └──→ Profile Node ───→ Update preferences
       │
       ▼
┌─────────────┐
│     END     │
└─────────────┘
```

## Memory Architecture

### Three Tiers

1. **Working Memory** (ephemeral)
   - Current node state
   - Temporary variables
   - Cleared after task completion

2. **Session Memory** (in-memory)
   - Files: {filepath: content} (max 30)
   - Conversation: [{q, a}] (max 10)
   - Accessed: set of filepaths
   - Eviction: LRU when limit exceeded

3. **Persistent Memory** (disk)
   - Preferences: {key: value}
   - Cache: {code_hash:query_hash: response} (max 500)
   - File hashes: {filepath: hash}
   - Eviction: Keep most recent 300 when > 500

### Cache Strategy

**Lookup**:
1. Exact match: same code_hash + query_hash
2. Similar match: same code_hash + 70%+ word overlap

**Invalidation**:
- Automatic when file content changes (hash mismatch)
- Manual eviction when cache size > 500

### Context Building

```python
def get_context(files, max_chars=40000):
    context = []
    
    # Add recent conversation (if any)
    context.append(last_3_conversations)
    
    # Add files with compression
    for file in files:
        if len(content) > available_space:
            # Compress: keep imports + signatures
            content = compress(content)
        context.append(content)
    
    return "\n\n".join(context)
```

## Tool Integration

### MCP Adapter Pattern

```python
class MCPAdapter:
    async def read_file(filepath):
        if mcp_available:
            try:
                return await mcp_client.call_tool("filesystem", "read_file", {path})
            except:
                pass
        
        # Fallback to direct
        return direct_read_file(filepath)
```

**Benefits**:
- MCP optional, not required
- Graceful degradation
- Easy to add new MCP servers
- Clean separation of concerns

## Edit Flow

```
1. User: "Add validation to create_task"
   ↓
2. Intent Node: Classifies as "edit"
   ↓
3. Edit Node:
   - Select relevant files (LLM)
   - Read file contents
   - Generate edit plan (LLM)
   - Store in pending_edits
   - Show plan to user
   ↓
4. User: "approve"
   ↓
5. Apply Edits:
   - Backup original file
   - Apply line edits
   - Save to disk
   - Update session memory
   ↓
6. Run Tests:
   - Execute pytest
   - Show results
```

## Error Handling

- All nodes return AgentState (no exceptions)
- Errors stored in state.error
- User sees error message
- No automatic retries (user decides)

## Undo Mechanism

```python
edit_history = [
    {
        "file": "routes/tasks.py",
        "backup": "original content",
        "timestamp": "2024-01-01T12:00:00"
    }
]

def undo():
    last_edit = edit_history.pop()
    restore_file(last_edit["file"], last_edit["backup"])
```

## Performance

- **File caching**: Avoid re-reading (session memory)
- **Response caching**: Avoid re-computing (persistent memory)
- **Lazy loading**: Only read files when needed
- **Compression**: Fit more context in LLM window
- **Similarity matching**: Higher cache hit rate

## Scalability

**Current limits**:
- 30 files in session
- 40K chars context
- 500 cache entries

**For larger codebases**:
- Increase session file limit
- Add file relevance scoring
- Implement chunking for large files
- Use embeddings for file selection

