"""Export verified patch examples from development runs without private model reasoning."""

import json
import sqlite3
from pathlib import Path


def export_verified(database: Path, output: Path) -> int:
    connection = sqlite3.connect(database)
    count = 0
    try:
        with output.open("w", encoding="utf-8") as handle:
            for run_id, issue_json in connection.execute("SELECT run_id, issue FROM runs WHERE status='SUCCEEDED'"):
                events = [json.loads(row[0]) for row in connection.execute(
                    "SELECT payload FROM events WHERE run_id=? ORDER BY sequence", (run_id,))]
                final = events[-1]
                baseline = next((event for event in events if event["stage"] == "BASELINE_RESULT"), None)
                tested = [event for event in events if event["stage"] == "TESTED"
                          and event["evidence"].get("execution_id") == final["evidence"].get("execution_id")]
                # Exclude scripted fixture results from training data.
                if not baseline or baseline["evidence"].get("status") != "TEST_FAILED" or not tested:
                    continue
                result = tested[-1]["evidence"]
                if result.get("status") != "PASSED" or result.get("image_id") == "trusted-fixture-host":
                    continue
                issue = json.loads(issue_json)
                item = {"run_id": run_id, "repository": issue["repository"],
                        "messages": [{"role": "user", "content": issue["description"]},
                                     {"role": "assistant", "content": final["diff"]}],
                        "verification": result}
                handle.write(json.dumps(item) + "\n")
                count += 1
    finally:
        connection.close()
    return count
