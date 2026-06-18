import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TRACE_LOG_PATH = Path("logs/agent_traces.jsonl")


def load_records(trace_id: str) -> List[Dict[str, Any]]:
    if not TRACE_LOG_PATH.exists():
        raise RuntimeError("找不到 logs/agent_traces.jsonl")

    records = []

    for line in TRACE_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        record = json.loads(line)

        if record.get("trace_id") == trace_id:
            records.append(record)

    return records


def print_trace(records: List[Dict[str, Any]]) -> None:
    spans = [r for r in records if r.get("type") == "span"]
    events = [r for r in records if r.get("type") == "event"]

    spans_by_parent = {}

    for span in spans:
        parent = span.get("parent_span_id")
        spans_by_parent.setdefault(parent, []).append(span)

    events_by_parent = {}

    for event in events:
        parent = event.get("parent_span_id")
        events_by_parent.setdefault(parent, []).append(event)

    def walk(parent_id=None, indent=0):
        children = spans_by_parent.get(parent_id, [])

        for span in children:
            prefix = "  " * indent
            print(
                f"{prefix}- {span['name']} "
                f"[{span['kind']}] "
                f"{span['status']} "
                f"{span['duration_ms']}ms"
            )

            for event in events_by_parent.get(span["span_id"], []):
                print(
                    f"{prefix}  * event: {event['name']} "
                    f"{json.dumps(event.get('attributes', {}), ensure_ascii=False)}"
                )

            walk(span["span_id"], indent + 1)

    walk(None)


def main() -> None:
    if len(sys.argv) != 2:
        print("用法：python view_trace.py <trace_id>")
        raise SystemExit(1)

    trace_id = sys.argv[1]
    records = load_records(trace_id)

    if not records:
        print(f"没有找到 trace_id：{trace_id}")
        return

    print(f"Trace: {trace_id}")
    print("=" * 80)
    print_trace(records)


if __name__ == "__main__":
    main()
