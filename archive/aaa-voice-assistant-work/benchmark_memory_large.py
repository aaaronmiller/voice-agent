
import time
import json
import os
import uuid
from src.memory_store import MemoryStore

DB_PATH = "memory/conversations_bench_large.jsonl"

def setup_data():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # Create a store just to use its logic or manually write
    # We want lots of old data

    print("Generating large data (500k lines)...")
    with open(DB_PATH, "w") as f:
        # Write 500,000 old lines
        # Using a fixed string to speed up generation
        entry_template = {
            "timestamp": "2023-01-01T00:00:00",
            "session_id": "old_session",
            "role": "user",
            "content": "Old message "
        }
        json_str = json.dumps(entry_template)

        chunk = (json_str + "\n") * 1000
        for i in range(500):
            f.write(chunk)

    # Now add current session data
    # We need to append manually or use MemoryStore
    entry = {
        "timestamp": "2023-01-01T00:00:00",
        "session_id": "current_session",
        "role": "user",
        "content": "New message"
    }
    with open(DB_PATH, "a") as f:
        for i in range(20):
            entry["content"] = f"New message {i}"
            f.write(json.dumps(entry) + "\n")

    return "current_session"

def run_benchmark():
    session_id = setup_data()
    ms = MemoryStore(DB_PATH)

    print("Starting benchmark...")
    start_time = time.time()
    # Run 10 times
    for _ in range(10):
        _ = ms.get_recent_history(limit=10, session_id=session_id)
    end_time = time.time()

    avg_time = (end_time - start_time) / 10
    print(f"Average time per call (500k lines): {avg_time:.6f} seconds")

    # Cleanup
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

if __name__ == "__main__":
    run_benchmark()
