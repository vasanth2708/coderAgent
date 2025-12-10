# Production Deployment Notes

## Memory Management

### What We Store

**Session Memory** (in-memory, cleared on restart):
- ✅ Last 10 conversations (for immediate context)
- ✅ Last 30 files accessed
- ✅ Current task state

**Persistent Memory** (disk, survives restart):
- ✅ User preferences
- ✅ Last 300 cached responses (with code hashes)
- ✅ Last 20 useful conversations (filtered)

### What We DON'T Store

❌ **Sensitive Information**:
- API keys, passwords, tokens
- Private keys, credentials
- Authorization headers

❌ **Generic Errors**:
- "File not found" errors
- Timeout errors
- Short error messages

❌ **Redundant Data**:
- Duplicate conversations
- Old cache entries (> 500)
- Stale file contents

### Privacy & Security

1. **Sensitive Data Filtering**:
   ```python
   if contains_sensitive_info(text):
       text = "[REDACTED]"
   ```

2. **Selective Persistence**:
   - Only useful conversations saved to disk
   - Generic errors stay in session only
   - Automatic cleanup of old data

3. **Size Limits**:
   - Session: 10 conversations, 30 files
   - Persistent: 20 conversations, 300 cache entries
   - Prevents unbounded growth

## Production Checklist

### Before Deployment

- [ ] Set `DEEPSEEK_API_KEY` environment variable
- [ ] Review `.memory.json` location (ensure writable)
- [ ] Configure `PROJECT_DIR` in config
- [ ] Test MCP servers (optional, fallback works)
- [ ] Set up logging/monitoring
- [ ] Review memory limits (adjust if needed)

### Security

- [ ] Don't log API keys
- [ ] Sanitize user inputs
- [ ] Validate file paths (prevent directory traversal)
- [ ] Limit command execution (whitelist if possible)
- [ ] Review sensitive data filters

### Performance

- [ ] Monitor memory usage
- [ ] Set appropriate cache sizes
- [ ] Consider Redis for distributed caching
- [ ] Add rate limiting for API calls
- [ ] Monitor DeepSeek API costs

### Monitoring

```python
# Add these metrics
- conversations_per_hour
- cache_hit_rate
- memory_file_size
- mcp_server_uptime
- deepseek_api_latency
- error_rate
```

## Configuration for Production

```python
# config.py - Production settings
MAX_SESSION_FILES = 30        # Adjust based on memory
MAX_CONVERSATION_HISTORY = 10  # Session only
MAX_PERSISTENT_CONV = 20      # Disk storage
CACHE_SIZE = 300              # Reduced from 500
COMMAND_TIMEOUT = 30          # Prevent hanging
```

## Cost Management

### DeepSeek API Costs

**Current pricing**:
- Input: $0.14 per 1M tokens
- Output: $0.28 per 1M tokens

**Typical session** (10 interactions):
- Input: ~50K tokens = $0.007
- Output: ~10K tokens = $0.003
- **Total: $0.01 per session**

**Monthly estimate** (1000 sessions):
- Cost: $10/month
- vs GPT-4o: $225/month
- **Savings: $215/month (95%)**

### Cost Optimization

1. **Cache aggressively**: 70% similarity matching
2. **Compress context**: Keep imports + signatures only
3. **Limit conversation history**: Don't send all history to LLM
4. **Use fast model**: DeepSeek-chat for all tasks

## Scaling Considerations

### Single Instance
- Current setup works for 1-10 concurrent users
- Memory: ~100MB per user session
- CPU: Minimal (mostly I/O bound)

### Multiple Instances
- Share `.memory.json` via Redis/database
- Separate MCP servers per instance
- Load balance at API gateway

### High Volume
- Move to distributed cache (Redis)
- Separate MCP server cluster
- Add request queuing
- Implement rate limiting

## Error Handling

### What We Log
- ✅ MCP server failures (with fallback)
- ✅ LLM API errors
- ✅ File operation errors
- ✅ Command execution failures

### What We Don't Log
- ❌ Sensitive user data
- ❌ API keys
- ❌ File contents (unless error)

## Backup & Recovery

### Memory File
- Location: `agent-v2/.memory.json`
- Backup: Daily (automated)
- Recovery: Automatic fallback to empty state

### User Data
- No user data stored (stateless)
- Conversations cleared on restart (session only)
- Persistent memory: preferences + cache only

## Compliance

### GDPR Considerations
- No personal data stored
- Conversations not persisted (except useful ones)
- Right to be forgotten: Delete `.memory.json`
- Data minimization: Only store what's needed

### Data Retention
- Session: Cleared on restart
- Persistent: 20 conversations max
- Cache: 300 entries max (auto-evicted)
- Logs: Rotate daily, keep 7 days

## Maintenance

### Regular Tasks
- Monitor `.memory.json` size (should be < 1MB)
- Check MCP server health
- Review error logs
- Update dependencies monthly

### Cleanup
```bash
# Clear all memory
rm agent-v2/.memory.json

# Restart MCP servers
# (automatic on agent restart)
```

## Support

### Common Issues

1. **Memory file too large**:
   - Reduce `MAX_PERSISTENT_CONV` to 10
   - Reduce `CACHE_SIZE` to 200

2. **MCP servers not starting**:
   - Check Node.js installed (for filesystem)
   - Check Python 3 available (for execution)
   - Agent works with fallback

3. **High API costs**:
   - Increase cache hit rate
   - Reduce conversation history
   - Compress context more aggressively

## Summary

**Production-ready features**:
- ✅ Sensitive data filtering
- ✅ Selective persistence
- ✅ Size limits
- ✅ Privacy-aware
- ✅ Cost-optimized
- ✅ Graceful degradation
- ✅ Error handling

**Not production-ready** (would need):
- ❌ Distributed caching
- ❌ Rate limiting
- ❌ Authentication/authorization
- ❌ Audit logging
- ❌ Metrics/monitoring
- ❌ Load balancing

