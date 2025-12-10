# Quick Start

## Setup (2 minutes)

```bash
# 1. Install dependencies
cd agent-v2
pip install -r requirements.txt

# 2. Set DeepSeek API key (get from https://platform.deepseek.com/)
export DEEPSEEK_API_KEY="sk-..."

# 3. Run
python main.py
```

## Example Session

```
AI Coding Agent (DeepSeek-Powered)
--------------------------------------------------

You: What does the create_task function do?

Agent: The create_task function in routes/tasks.py creates a new task...
[Reads relevant files, provides answer]

You: Add input validation to check if title is not empty

Agent: Edit plan for routes/tasks.py:
- Lines 15-20: Add validation check
Type 'approve' to apply these edits.

You: approve

Agent: Applied edits to routes/tasks.py
Tests passed!

You: undo

Agent: Reverted changes to routes/tasks.py
```

## Commands

- **Read**: "What does X do?", "Show me the auth code"
- **Edit**: "Add validation", "Fix the bug in X"
- **Run**: "Run tests", "Execute pytest"
- **Undo**: "undo", "revert"
- **Profile**: "Always add comments"
- **Exit**: "exit", "quit"

## Architecture at a Glance

```
User → Intent Classification → Route → Execute → Response
                                  ↓
                    ┌─────────────┴─────────────┐
                    │                           │
                  Read                        Edit
                    │                           │
              Answer question            Generate plan
                                              ↓
                                         User approves
                                              ↓
                                         Apply edits
                                              ↓
                                          Run tests
```

## Memory System

- **Session**: Last 30 files + 10 conversations
- **Cache**: 500 responses (survives restarts)
- **Compression**: Automatic for large files

## That's It!

No complex setup. No configuration files. Just install and run.

