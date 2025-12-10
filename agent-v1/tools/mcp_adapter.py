"""
MCP Adapter - Routes tool calls through MCP when available, falls back to direct

This provides the MCP integration layer while keeping tools functional
"""
import json
from typing import Any, Dict, List, Optional

from tools.filesystem import list_files as direct_list_files
from tools.filesystem import read_file as direct_read_file
from tools.filesystem import write_file as direct_write_file
from tools.execution import run_command as direct_run_command


class MCPAdapter:
    """
    Adapter that tries MCP first, falls back to direct tools
    
    MCP servers are initialized in main.py
    """
    
    def __init__(self):
        self.mcp_available = False
        self.mcp_client = None
    
    def set_mcp_client(self, client):
        """Set MCP client after initialization"""
        self.mcp_client = client
        self.mcp_available = client is not None and len(client.servers) > 0
        if self.mcp_available:
            tools = client.get_all_tools()
            print(f"✓ MCP Adapter: {len(client.servers)} servers, {sum(len(t) for t in tools.values())} tools")
            print(f"  Servers: {', '.join(tools.keys())}")
            print(f"  Note: Automatic fallback to direct tools if MCP fails")
    
    async def list_files(self) -> List[str]:
        """List files via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                # Try MCP filesystem server with list_directory
                result = await self.mcp_client.call_tool(
                    "filesystem",
                    "list_directory",
                    {"path": "."}
                )
                
                if result and "content" in result:
                    content = result["content"][0]["text"]
                    
                    # Try to parse as JSON
                    try:
                        if isinstance(content, str):
                            files = json.loads(content)
                        else:
                            files = content
                        
                        # Filter for Python files
                        if isinstance(files, list):
                            return [f for f in files if isinstance(f, str) and f.endswith(".py")]
                    except json.JSONDecodeError:
                        # Content might be plain text list
                        if isinstance(content, str):
                            lines = content.strip().split('\n')
                            return [f.strip() for f in lines if f.strip().endswith(".py")]
                
            except Exception as e:
                # Silently fall back (don't spam console)
                pass
        
        # Fallback to direct
        return direct_list_files()
    
    async def read_file(self, filepath: str) -> str:
        """Read file via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                result = await self.mcp_client.call_tool(
                    "filesystem",
                    "read_file",
                    {"path": filepath}
                )
                if result and "content" in result:
                    content = result["content"][0]["text"]
                    if content:
                        return content
            except Exception:
                # Silently fall back
                pass
        
        # Fallback to direct
        return direct_read_file(filepath)
    
    async def write_file(self, filepath: str, content: str):
        """Write file via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                result = await self.mcp_client.call_tool(
                    "filesystem",
                    "write_file",
                    {"path": filepath, "content": content}
                )
                if result:
                    return
            except Exception:
                # Silently fall back
                pass
        
        # Fallback to direct
        direct_write_file(filepath, content)
    
    async def run_command(self, command: List[str]) -> Dict[str, Any]:
        """Run command via MCP or direct"""
        if self.mcp_available and "execution" in self.mcp_client.servers:
            try:
                result = await self.mcp_client.call_tool(
                    "execution",
                    "execute_command",
                    {"command": command}
                )
                if result and "content" in result:
                    content = result["content"][0]["text"]
                    parsed = json.loads(content) if isinstance(content, str) else content
                    if isinstance(parsed, dict):
                        return parsed
            except Exception:
                # Silently fall back
                pass
        
        # Fallback to direct
        return direct_run_command(command)


# Global adapter instance
mcp_adapter = MCPAdapter()

