#!/usr/bin/env python3
"""
MCP Filesystem Server - Provides filesystem operations via MCP protocol
"""
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "sampleProject"


def send_response(response):
    """Send JSON-RPC response"""
    print(json.dumps(response), flush=True)
    sys.stderr.write(f"[FS-SERVER] Sent: {json.dumps(response)[:100]}\n")
    sys.stderr.flush()


def handle_initialize(request_id):
    """Handle initialize request"""
    sys.stderr.write(f"[FS-SERVER] Initializing...\n")
    sys.stderr.flush()
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "filesystem-server", "version": "1.0"}
        }
    })


def handle_tools_list(request_id):
    """Handle tools/list request"""
    sys.stderr.write(f"[FS-SERVER] Listing tools...\n")
    sys.stderr.flush()
    send_response({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file's contents",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to file"
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "write_file",
                    "description": "Write content to a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to file"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write"
                            }
                        },
                        "required": ["path", "content"]
                    }
                },
                {
                    "name": "list_directory",
                    "description": "List files in a directory",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path",
                                "default": "."
                            }
                        }
                    }
                }
            ]
        }
    })


def handle_tools_call(request_id, params):
    """Handle tools/call request"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    sys.stderr.write(f"[FS-SERVER] Calling tool: {tool_name} with args: {arguments}\n")
    sys.stderr.flush()
    
    try:
        if tool_name == "read_file":
            filepath = arguments.get("path", "")
            full_path = PROJECT_DIR / filepath
            content = full_path.read_text(encoding="utf-8")
            
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": content}]
                }
            })
            
        elif tool_name == "write_file":
            filepath = arguments.get("path", "")
            content = arguments.get("content", "")
            full_path = PROJECT_DIR / filepath
            full_path.write_text(content, encoding="utf-8")
            
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"Written to {filepath}"}]
                }
            })
            
        elif tool_name == "list_directory":
            dirpath = arguments.get("path", ".")
            full_path = PROJECT_DIR / dirpath
            
            files = []
            for root, _, filenames in os.walk(full_path):
                for f in filenames:
                    if f.endswith(".py"):
                        rel = str(Path(root, f).relative_to(PROJECT_DIR))
                        files.append(rel)
            
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(sorted(files))}]
                }
            })
        else:
            send_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -1, "message": f"Unknown tool: {tool_name}"}
            })
    except Exception as e:
        sys.stderr.write(f"[FS-SERVER] Error: {e}\n")
        sys.stderr.flush()
        send_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -1, "message": str(e)}
        })


def main():
    """Main server loop"""
    sys.stderr.write(f"[FS-SERVER] Starting filesystem server for {PROJECT_DIR}\n")
    sys.stderr.flush()
    
    for line in sys.stdin:
        try:
            sys.stderr.write(f"[FS-SERVER] Received: {line.strip()}\n")
            sys.stderr.flush()
            
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
            sys.stderr.write(f"[FS-SERVER] Error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()

