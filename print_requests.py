import json
import os

trace_file = r"e:\AILearn\20260321codexconsole\codex-console\data\universal_trace.jsonl"

def print_first_requests():
    if not os.path.exists(trace_file):
        print(f"File not found: {trace_file}")
        return

    count = 0
    with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                if data.get('type') == 'request':
                    url = data.get('url', '')
                    if 'openai.com' in url or 'chatgpt.com' in url:
                        print(f"Line {i}: {data['method']} {url}")
                        count += 1
                        if count > 100:
                            break
            except Exception:
                pass

if __name__ == "__main__":
    print_first_requests()
