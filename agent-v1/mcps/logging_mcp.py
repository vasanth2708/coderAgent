from datetime import datetime
from typing import Any, Dict

from mcps.memory_mcp import save_memory


def log_node_execution(mem: Dict[str, Any], node_name: str, input_summary: Dict[str, Any], 
                       output_summary: Dict[str, Any], duration: float) -> None:
    node_log = mem.setdefault("node_log", [])
    
    log_entry = {
        "node_name": node_name,
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": round(duration, 3),
        "input": input_summary,
        "output": output_summary
    }
    
    node_log.append(log_entry)
    
    if len(node_log) > 1000:
        node_log[:] = node_log[-1000:]
    
    if len(node_log) % 10 == 0 or node_name in ["edit", "read", "run_tests"]:
        save_memory(mem)
        print(f"  [NODE_LOG] Logged {node_name} execution (total: {len(node_log)} entries)")

