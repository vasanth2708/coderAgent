"""
MCP Client - Manages connections to MCP servers
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "sampleProject"


class MCPServer:
    """Represents a single MCP server connection"""
    
    def __init__(self, name: str, command: List[str]):
        self.name = name
        self.command = command
        self.process: Optional[subprocess.Popen] = None
        self.tools: Dict[str, Any] = {}
    
    async def start(self) -> bool:
        """Start the MCP server"""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_DIR
            )
            
            # Give server time to start
            await asyncio.sleep(0.5)
            
            # Initialize
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "coding-agent", "version": "1.0"}
                }
            }
            
            self.process.stdin.write(json.dumps(init_request) + "\n")
            self.process.stdin.flush()
            
            # Read response with timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=5.0
            )
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result:
                        # Discover tools
                        await self.discover_tools()
                        return True
                except json.JSONDecodeError as e:
                    print(f"Failed to parse init response from {self.name}: {e}")
                    print(f"Response was: {response[:100]}")
            
            return False
        except asyncio.TimeoutError:
            print(f"Timeout waiting for {self.name} to initialize")
            return False
        except Exception as e:
            print(f"Failed to start MCP server {self.name}: {e}")
            return False
    
    async def discover_tools(self):
        """Discover available tools from server"""
        try:
            tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            
            self.process.stdin.write(json.dumps(tools_request) + "\n")
            self.process.stdin.flush()
            
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=5.0
            )
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result and "tools" in result["result"]:
                        for tool in result["result"]["tools"]:
                            self.tools[tool["name"]] = tool
                except json.JSONDecodeError as e:
                    print(f"Failed to parse tools list from {self.name}: {e}")
        except asyncio.TimeoutError:
            print(f"Timeout discovering tools from {self.name}")
        except Exception as e:
            print(f"Failed to discover tools from {self.name}: {e}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on this server"""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=10.0
            )
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result:
                        return result["result"]
                    elif "error" in result:
                        print(f"MCP error from {self.name}: {result['error']}")
                        return None
                except json.JSONDecodeError as e:
                    print(f"Failed to parse tool response from {self.name}: {e}")
                    print(f"Response was: {response[:200]}")
            
            return None
        except asyncio.TimeoutError:
            print(f"Timeout calling tool {tool_name} on {self.name}")
            return None
        except Exception as e:
            print(f"Failed to call tool {tool_name}: {e}")
            return None
    
    def stop(self):
        """Stop the MCP server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)


class MCPClient:
    """Manages multiple MCP server connections"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
    
    async def add_server(self, name: str, command: List[str]) -> bool:
        """Add and start an MCP server"""
        server = MCPServer(name, command)
        if await server.start():
            self.servers[name] = server
            print(f"✓ MCP server '{name}' started with {len(server.tools)} tools")
            return True
        else:
            print(f"✗ Failed to start MCP server '{name}'")
            return False
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on a specific server"""
        if server_name not in self.servers:
            return None
        
        return await self.servers[server_name].call_tool(tool_name, arguments)
    
    def get_all_tools(self) -> Dict[str, List[str]]:
        """Get all available tools from all servers"""
        result = {}
        for server_name, server in self.servers.items():
            result[server_name] = list(server.tools.keys())
        return result
    
    def stop_all(self):
        """Stop all MCP servers"""
        for server in self.servers.values():
            server.stop()


# Global MCP client instance
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> Optional[MCPClient]:
    """Get the global MCP client"""
    return _mcp_client


async def initialize_mcp() -> MCPClient:
    """Initialize MCP client with servers"""
    global _mcp_client
    
    _mcp_client = MCPClient()
    
    # Try to add filesystem server (Node.js based)
    # Note: This requires Node.js and npx to be installed
    try:
        # Check if npx is available
        result = subprocess.run(["which", "npx"], capture_output=True)
        if result.returncode == 0:
            await _mcp_client.add_server(
                "filesystem",
                ["npx", "-y", "@modelcontextprotocol/server-filesystem", str(PROJECT_DIR)]
            )
        else:
            print("Note: npx not found, skipping filesystem MCP server (using direct fallback)")
    except Exception as e:
        print(f"Note: Filesystem MCP server not available: {e}")
    
    # Try to add execution server (Python based)
    try:
        execution_server = Path(__file__).parent / "execution_server.py"
        if execution_server.exists():
            await _mcp_client.add_server(
                "execution",
                [sys.executable, str(execution_server)]
            )
        else:
            print(f"Note: Execution server not found at {execution_server}")
    except Exception as e:
        print(f"Note: Execution MCP server not available: {e}")
    
    return _mcp_client

