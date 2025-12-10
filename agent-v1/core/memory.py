"""Memory Management"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_FILE = BASE_DIR / ".memory.json"


class Memory:
    """Unified memory manager with intelligent caching and compression"""
    
    def __init__(self):
        self.persistent = self._load_persistent()
        self.session = {
            "files": {},  # filepath -> content
            "conversation": [],  # Recent Q&A pairs
            "accessed": set()  # Track accessed files
        }
        self.working = {}  # Current task state
    
    def _load_persistent(self) -> Dict[str, Any]:
        """Load persistent memory from disk"""
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except:
                pass
        return {
            "preferences": {},
            "cache": {},  # code_hash:query_hash -> response
            "file_hashes": {}  # filepath -> hash
        }
    
    def save(self):
        """Save persistent memory to disk with size management"""
        # Limit cache size
        if len(self.persistent.get("cache", {})) > 500:
            # Keep most recent 300
            items = sorted(
                self.persistent["cache"].items(),
                key=lambda x: x[1].get("timestamp", ""),
                reverse=True
            )
            self.persistent["cache"] = dict(items[:300])
        
        # Limit conversation history
        if len(self.persistent.get("recent_conversations", [])) > 20:
            self.persistent["recent_conversations"] = self.persistent["recent_conversations"][-20:]
        
        # Write to disk
        try:
            MEMORY_FILE.write_text(json.dumps(self.persistent, indent=2))
        except Exception as e:
            # Don't crash if we can't save memory
            print(f"Warning: Could not save memory: {e}")
    
    def compute_hash(self, files: Dict[str, str]) -> str:
        """Compute hash from file contents"""
        content = "".join(f"{k}:{v}" for k, v in sorted(files.items()))
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def get_cached(self, code_hash: str, query: str) -> Optional[str]:
        """Get cached response with similarity matching"""
        cache = self.persistent["cache"]
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        key = f"{code_hash}:{query_hash}"
        
        # Exact match
        if key in cache:
            return cache[key]["response"]
        
        # Similar query match (simple word overlap)
        query_words = set(query.lower().split())
        for cached_key, cached_val in cache.items():
            if cached_key.startswith(code_hash):
                cached_query = cached_val.get("query", "")
                cached_words = set(cached_query.lower().split())
                overlap = len(query_words & cached_words) / max(len(query_words), 1)
                if overlap > 0.7:  # 70% similarity
                    return cached_val["response"]
        
        return None
    
    def cache_response(self, code_hash: str, query: str, response: str):
        """
        Cache response with similarity deduplication.
        
        If a very similar query exists for the same code hash, update it instead
        of creating a duplicate entry.
        """
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        key = f"{code_hash}:{query_hash}"
        
        # Check for similar existing queries (70% word overlap)
        query_words = set(query.lower().split())
        cache = self.persistent["cache"]
        
        for existing_key, existing_val in list(cache.items()):
            # Only check entries with same code hash
            if existing_key.startswith(code_hash):
                existing_query = existing_val.get("query", "")
                existing_words = set(existing_query.lower().split())
                
                # Calculate similarity
                if query_words and existing_words:
                    overlap = len(query_words & existing_words) / max(len(query_words), len(existing_words))
                    
                    if overlap > 0.7:  # 70% similarity
                        # Update existing entry instead of creating duplicate
                        cache[existing_key] = {
                            "query": query,  # Update with latest query
                            "response": response[:5000],
                            "timestamp": datetime.now().isoformat()
                        }
                        self.save()
                        return
        
        # No similar entry found, create new one
        cache[key] = {
            "query": query,
            "response": response[:5000],
            "timestamp": datetime.now().isoformat()
        }
        self.save()
    
    def add_file(self, filepath: str, content: str):
        """Add file to session memory"""
        self.session["files"][filepath] = content
        self.session["accessed"].add(filepath)
        
        # Limit session files to 30 most recent
        if len(self.session["files"]) > 30:
            # Remove least recently accessed
            accessed_list = list(self.session["accessed"])
            to_remove = accessed_list[:-30]
            for f in to_remove:
                self.session["files"].pop(f, None)
                self.session["accessed"].discard(f)
    
    def add_conversation(self, question: str, answer: str):
        """
        Add conversation entry with production-grade filtering.
        
        Production rules:
        - Store successful interactions for context
        - Store errors only if they contain useful info (not sensitive data)
        - Limit storage to prevent memory bloat
        - Don't persist sensitive information
        """
        # Filter out sensitive information
        if self._contains_sensitive_info(question) or self._contains_sensitive_info(answer):
            # Store sanitized version
            question = "[REDACTED - contains sensitive info]"
            answer = "[REDACTED - contains sensitive info]"
        
        # Session memory: Keep last 10 for immediate context
        self.session["conversation"].append({
            "q": question[:300],
            "a": answer[:1000],
            "timestamp": datetime.now().isoformat()
        })
        if len(self.session["conversation"]) > 10:
            self.session["conversation"] = self.session["conversation"][-10:]
        
        # Persistent memory: Only store successful/useful interactions
        # Skip generic errors or repeated failures
        if not self._should_skip_persistent(answer):
            self.persistent.setdefault("recent_conversations", []).append({
                "q": question[:200],  # Shorter for persistent
                "a": answer[:300],    # Shorter for persistent
                "timestamp": datetime.now().isoformat()
            })
            # Keep last 20 in persistent (not 50)
            if len(self.persistent["recent_conversations"]) > 20:
                self.persistent["recent_conversations"] = self.persistent["recent_conversations"][-20:]
            self.save()
    
    def _contains_sensitive_info(self, text: str) -> bool:
        """Check if text contains sensitive information"""
        sensitive_patterns = [
            "password", "api_key", "secret", "token", "credential",
            "private_key", "ssh_key", "bearer", "authorization"
        ]
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in sensitive_patterns)
    
    def _should_skip_persistent(self, answer: str) -> bool:
        """Decide if we should skip persisting this conversation"""
        # Skip generic errors
        if answer.startswith("Error:") and len(answer) < 50:
            return True
        
        # Skip "No such file" errors (too common, not useful)
        if "No such file" in answer or "not found" in answer.lower():
            return True
        
        # Skip timeout errors
        if "timeout" in answer.lower() or "timed out" in answer.lower():
            return True
        
        return False
    
    def get_context(self, files: List[str], max_chars: int = 40000) -> str:
        """Build context from files with smart truncation"""
        parts = []
        total = 0
        
        # Add recent conversation (if any) - includes ALL conversations
        if self.session["conversation"]:
            conv = "\n".join([
                f"Q: {c['q']}\nA: {c['a'][:200]}..."  # Truncate long answers in context
                for c in self.session["conversation"][-3:]
            ])
            parts.append(f"# Recent Conversation (last 3 interactions)\n{conv}")
            total += len(conv)
        
        # Add files
        for filepath in files:
            content = self.session["files"].get(filepath, "")
            if not content:
                continue
            
            available = max_chars - total
            if available < 1000:
                break
            
            # Compress if needed
            if len(content) > available:
                # Keep structure: imports + function signatures
                lines = content.split("\n")
                kept = []
                for line in lines:
                    if line.strip().startswith(("import", "from", "def", "class", "async def")):
                        kept.append(line)
                    if len("\n".join(kept)) > available * 0.8:
                        break
                content = "\n".join(kept) + f"\n# ... (truncated {len(lines) - len(kept)} lines)"
            
            parts.append(f"# {filepath}\n{content}")
            total += len(content)
        
        return "\n\n".join(parts)

