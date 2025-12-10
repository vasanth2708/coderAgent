#!/usr/bin/env python3
"""
MCP Execution Server - Provides command execution via MCP protocol
"""
import json
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "sampleProject"


def send_response(response):
    """Send JSON-RPC response"""
    print(json.dumps(response), flush=True)


def handle_initialize(request_id):
    """Handle initialize request"""
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "execution-server", "version": "1.0"}
        }
    })


def handle_tools_list(request_id):
    """Handle tools/list request"""
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "execute_command",
                    "description": "Execute a shell command",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Command and arguments"
                            },
                            "timeout": {
                                "type": "number",
                                "description": "Timeout in seconds",
                                "default": 30
                            }
                        },
                        "required": ["command"]
                    }
                }
            ]
        }
    })


def handle_tools_call(request_id, params):
    """Handle tools/call request"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if tool_name == "execute_command":
        command = arguments.get("command", [])
        timeout = arguments.get("timeout", 30)
        
        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "success": result.returncode == 0
            }
            
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(output)}]
                }
            })
        except subprocess.TimeoutExpired:
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -1,
                    "message": f"Command timed out after {timeout}s"
                }
            })
        except Exception as e:
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -1, "message": str(e)}
            })
    else:
        send_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -1, "message": f"Unknown tool: {tool_name}"}
        })


def main():
    """Main server loop"""
    for line in sys.stdin:
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            if method == "initialize":
                handle_initialize(request_id)
            elif method == "tools/list":
                handle_tools_list(request_id)
            elif method == "tools/call":
                handle_tools_call(request_id, params)
            else:
                send_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -1, "message": f"Unknown method: {method}"}
                })
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

