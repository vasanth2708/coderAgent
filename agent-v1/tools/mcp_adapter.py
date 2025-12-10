"""
MCP Adapter - Routes tool calls through MCP when available, falls back to direct

This provides the MCP integration layer while keeping tools functional
"""
import json
from typing import Any, Dict, List, Optional

from tools.filesystem import list_files as direct_list_files
from tools.filesystem import read_file as direct_read_file
from tools.filesystem import write_file as direct_write_file
from tools.filesystem import backup_file as direct_backup_file
from tools.filesystem import restore_file as direct_restore_file
from tools.execution import run_command as direct_run_command

# Enable adapter debug logging
ADAPTER_DEBUG = True

def adapter_log(msg: str):
    """Log adapter operations"""
    if ADAPTER_DEBUG:
        print(f"[MCP-ADAPTER] {msg}")


class MCPAdapter:
    """
    Adapter that tries MCP first, falls back to direct tools
    
    MCP servers are initialized in main.py
    """
    
    def __init__(self):
        self.mcp_available = False
        self.mcp_client = None
        self.mcp_success_count = 0
        self.fallback_count = 0
    
    def set_mcp_client(self, client):
        """Set MCP client after initialization"""
        self.mcp_client = client
        self.mcp_available = client is not None and len(client.servers) > 0
        if self.mcp_available:
            tools = client.get_all_tools()
            adapter_log(f"✓ MCP Adapter ready: {len(client.servers)} servers, {sum(len(t) for t in tools.values())} tools")
            adapter_log(f"  Servers: {', '.join(tools.keys())}")
            adapter_log(f"  Will use MCP first, fallback to direct if needed")
        else:
            adapter_log("⚠ MCP not available - using direct tools only")
    
    def get_stats(self):
        """Get adapter statistics"""
        return {
            "mcp_success": self.mcp_success_count,
            "fallback": self.fallback_count,
            "total": self.mcp_success_count + self.fallback_count
        }
    
    async def list_files(self) -> List[str]:
        """List files via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                adapter_log("Attempting list_files via MCP")
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
                            self.mcp_success_count += 1
                            adapter_log(f"✓ MCP list_files succeeded: {len(files)} files")
                            return [f for f in files if isinstance(f, str) and f.endswith(".py")]
                    except json.JSONDecodeError:
                        # Content might be plain text list
                        if isinstance(content, str):
                            lines = content.strip().split('\n')
                            result_files = [f.strip() for f in lines if f.strip().endswith(".py")]
                            self.mcp_success_count += 1
                            adapter_log(f"✓ MCP list_files succeeded: {len(result_files)} files")
                            return result_files
                
            except Exception as e:
                adapter_log(f"✗ MCP list_files failed: {e}, falling back to direct")
                self.fallback_count += 1
        else:
            self.fallback_count += 1
        
        # Fallback to direct
        adapter_log("Using direct list_files")
        return direct_list_files()
    
    async def read_file(self, filepath: str) -> str:
        """Read file via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                adapter_log(f"Attempting read_file via MCP: {filepath}")
                result = await self.mcp_client.call_tool(
                    "filesystem",
                    "read_file",
                    {"path": filepath}
                )
                if result and "content" in result:
                    content = result["content"][0]["text"]
                    if content:
                        self.mcp_success_count += 1
                        adapter_log(f"✓ MCP read_file succeeded: {filepath} ({len(content)} chars)")
                        return content
            except Exception as e:
                adapter_log(f"✗ MCP read_file failed: {e}, falling back to direct")
                self.fallback_count += 1
        else:
            self.fallback_count += 1
        
        # Fallback to direct
        adapter_log(f"Using direct read_file: {filepath}")
        return direct_read_file(filepath)
    
    async def write_file(self, filepath: str, content: str):
        """Write file via MCP or direct"""
        if self.mcp_available and "filesystem" in self.mcp_client.servers:
            try:
                adapter_log(f"Attempting write_file via MCP: {filepath}")
                result = await self.mcp_client.call_tool(
                    "filesystem",
                    "write_file",
                    {"path": filepath, "content": content}
                )
                if result:
                    self.mcp_success_count += 1
                    adapter_log(f"✓ MCP write_file succeeded: {filepath} ({len(content)} chars)")
                    return
            except Exception as e:
                adapter_log(f"✗ MCP write_file failed: {e}, falling back to direct")
                self.fallback_count += 1
        else:
            self.fallback_count += 1
        
        # Fallback to direct
        adapter_log(f"Using direct write_file: {filepath}")
        direct_write_file(filepath, content)
    
    async def run_command(self, command: List[str]) -> Dict[str, Any]:
        """Run command via MCP or direct"""
        if self.mcp_available and "execution" in self.mcp_client.servers:
            try:
                adapter_log(f"Attempting run_command via MCP: {' '.join(command)}")
                result = await self.mcp_client.call_tool(
                    "execution",
                    "execute_command",
                    {"command": command}
                )
                if result and "content" in result:
                    content = result["content"][0]["text"]
                    parsed = json.loads(content) if isinstance(content, str) else content
                    if isinstance(parsed, dict):
                        self.mcp_success_count += 1
                        adapter_log(f"✓ MCP run_command succeeded: {' '.join(command)}")
                        return parsed
            except Exception as e:
                adapter_log(f"✗ MCP run_command failed: {e}, falling back to direct")
                self.fallback_count += 1
        else:
            self.fallback_count += 1
        
        # Fallback to direct
        adapter_log(f"Using direct run_command: {' '.join(command)}")
        return direct_run_command(command)
    
    async def backup_file(self, filepath: str) -> str:
        """Backup file (read current content) via MCP or direct"""
        # Backup is just reading the current content
        return await self.read_file(filepath)
    
    async def restore_file(self, filepath: str, content: str):
        """Restore file from backup via MCP or direct"""
        # Restore is just writing the backup content
        await self.write_file(filepath, content)


# Global adapter instance
mcp_adapter = MCPAdapter()

