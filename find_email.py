import json
import os

trace_file = r"e:\AILearn\20260321codexconsole\codex-console\data\universal_trace.jsonl"
email = "kasia-hosh9520@hotmail.com"

def find_first_occurrence():
    if not os.path.exists(trace_file):
        print(f"File not found: {trace_file}")
        return

    with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            if email in line:
                try:
                    data = json.loads(line)
                    print(f"First occurrence at line {i}:")
                    print(f"  Type: {data.get('type')}")
                    if data.get('type') == 'request':
                        print(f"  Method: {data.get('method')}")
                        print(f"  URL: {data.get('url')}")
                    return i
                except:
                    print(f"First occurrence at line {i} (non-JSON or corrupted)")
                    return i
    print("Email not found")
    return None

if __name__ == "__main__":
    find_first_occurrence()
