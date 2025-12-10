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

# Enable MCP debug logging
MCP_DEBUG = True

def mcp_log(msg: str):
    """Log MCP operations"""
    if MCP_DEBUG:
        print(f"[MCP-CLIENT] {msg}")


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
            mcp_log(f"Starting server '{self.name}' with command: {' '.join(self.command)}")
            
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_DIR,
                bufsize=1  # Line buffered
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
            
            mcp_log(f"Sending initialize to {self.name}: {json.dumps(init_request)}")
            self.process.stdin.write(json.dumps(init_request) + "\n")
            self.process.stdin.flush()
            
            # Read response with timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=5.0
            )
            
            mcp_log(f"Received from {self.name}: {response.strip()[:200]}")
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result:
                        mcp_log(f"✓ Server {self.name} initialized successfully")
                        # Discover tools
                        await self.discover_tools()
                        return True
                    elif "error" in result:
                        mcp_log(f"✗ Server {self.name} returned error: {result['error']}")
                except json.JSONDecodeError as e:
                    mcp_log(f"✗ Failed to parse init response from {self.name}: {e}")
                    mcp_log(f"   Response was: {response[:100]}")
            
            return False
        except asyncio.TimeoutError:
            mcp_log(f"✗ Timeout waiting for {self.name} to initialize")
            # Check stderr for errors
            if self.process and self.process.stderr:
                stderr = self.process.stderr.read()
                if stderr:
                    mcp_log(f"   stderr: {stderr[:200]}")
            return False
        except Exception as e:
            mcp_log(f"✗ Failed to start MCP server {self.name}: {e}")
            import traceback
            mcp_log(f"   {traceback.format_exc()}")
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
            
            mcp_log(f"Discovering tools from {self.name}")
            self.process.stdin.write(json.dumps(tools_request) + "\n")
            self.process.stdin.flush()
            
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=5.0
            )
            
            mcp_log(f"Tools response from {self.name}: {response.strip()[:200]}")
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result and "tools" in result["result"]:
                        for tool in result["result"]["tools"]:
                            self.tools[tool["name"]] = tool
                        mcp_log(f"✓ Discovered {len(self.tools)} tools from {self.name}: {list(self.tools.keys())}")
                    elif "error" in result:
                        mcp_log(f"✗ Error discovering tools from {self.name}: {result['error']}")
                except json.JSONDecodeError as e:
                    mcp_log(f"✗ Failed to parse tools list from {self.name}: {e}")
        except asyncio.TimeoutError:
            mcp_log(f"✗ Timeout discovering tools from {self.name}")
        except Exception as e:
            mcp_log(f"✗ Failed to discover tools from {self.name}: {e}")
    
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
            
            mcp_log(f"Calling {tool_name} on {self.name} with args: {arguments}")
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            
            response = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline),
                timeout=10.0
            )
            
            mcp_log(f"Tool response from {self.name}: {response.strip()[:200]}")
            
            if response and response.strip():
                try:
                    result = json.loads(response.strip())
                    if "result" in result:
                        mcp_log(f"✓ Tool {tool_name} succeeded")
                        return result["result"]
                    elif "error" in result:
                        mcp_log(f"✗ MCP error from {self.name}: {result['error']}")
                        return None
                except json.JSONDecodeError as e:
                    mcp_log(f"✗ Failed to parse tool response from {self.name}: {e}")
                    mcp_log(f"   Response was: {response[:200]}")
            
            return None
        except asyncio.TimeoutError:
            mcp_log(f"✗ Timeout calling tool {tool_name} on {self.name}")
            return None
        except Exception as e:
            mcp_log(f"✗ Failed to call tool {tool_name}: {e}")
            return None
    
    def stop(self):
        """Stop the MCP server"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                mcp_log(f"Note: Error stopping server {self.name}: {e}")


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
    
    mcp_log("=" * 60)
    mcp_log("Initializing MCP Servers")
    mcp_log("=" * 60)
    
    # Add Python-based filesystem server
    try:
        filesystem_server = Path(__file__).parent / "filesystem_server.py"
        if filesystem_server.exists():
            mcp_log(f"Adding filesystem server from {filesystem_server}")
            success = await _mcp_client.add_server(
                "filesystem",
                [sys.executable, str(filesystem_server)]
            )
            if not success:
                mcp_log("✗ Filesystem server failed to start")
        else:
            mcp_log(f"✗ Filesystem server not found at {filesystem_server}")
    except Exception as e:
        mcp_log(f"✗ Filesystem MCP server error: {e}")
    
    # Add Python-based execution server
    try:
        execution_server = Path(__file__).parent / "execution_server.py"
        if execution_server.exists():
            mcp_log(f"Adding execution server from {execution_server}")
            success = await _mcp_client.add_server(
                "execution",
                [sys.executable, str(execution_server)]
            )
            if not success:
                mcp_log("✗ Execution server failed to start")
        else:
            mcp_log(f"✗ Execution server not found at {execution_server}")
    except Exception as e:
        mcp_log(f"✗ Execution MCP server error: {e}")
    
    mcp_log("=" * 60)
    if len(_mcp_client.servers) > 0:
        mcp_log(f"✓ MCP initialized with {len(_mcp_client.servers)} server(s)")
        for name, server in _mcp_client.servers.items():
            mcp_log(f"  • {name}: {len(server.tools)} tools")
    else:
        mcp_log("⚠ No MCP servers started - will use direct fallback")
    mcp_log("=" * 60)
    
    return _mcp_client

