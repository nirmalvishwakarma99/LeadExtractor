import os
import json
from typing import Dict, Any, Set

class ProgressManager:
    def __init__(self, progress_filepath: str):
        self.filepath = progress_filepath
        self.state: Dict[str, Any] = {
            "completed_queries": [],
            "completed_urls": [],
            "total_records_saved": 0,
            "last_checkpoint_index": 0
        }
        self.completed_urls_set: Set[str] = set()
        self.completed_queries_set: Set[str] = set()
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.state.update(data)
            except Exception:
                pass

        # Populate in-memory sets for O(1) lookups
        self.completed_urls_set = set(self.state.get("completed_urls", []))
        self.completed_queries_set = set(self.state.get("completed_queries", []))

    def save_atomic(self):
        self.state["completed_urls"] = list(self.completed_urls_set)
        self.state["completed_queries"] = list(self.completed_queries_set)
        
        temp_file = f"{self.filepath}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, self.filepath)

    def is_query_done(self, query: str) -> bool:
        return query in self.completed_queries_set

    def mark_query_done(self, query: str):
        if query not in self.completed_queries_set:
            self.completed_queries_set.add(query)
            self.save_atomic()

    def is_url_done(self, url: str) -> bool:
        return url in self.completed_urls_set

    def mark_url_done(self, url: str):
        self.completed_urls_set.add(url)