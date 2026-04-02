import json
import os

trace_file = r"e:\AILearn\20260321codexconsole\codex-console\data\universal_trace.jsonl"

def search_trace():
    if not os.path.exists(trace_file):
        print(f"File not found: {trace_file}")
        return

    with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                if data.get('type') == 'request' and data.get('method') == 'POST':
                    url = data.get('url', '')
                    if 'auth.openai.com' in url or 'chatgpt.com' in url:
                        # Exclude analytics if they are too many
                        if 'ces/v1' in url or 'datadoghq' in url:
                            continue
                        print(f"Line {i}: {data['method']} {url}")
                        # Print some post_data if possible
                        pd = data.get('post_data', '')
                        if pd:
                            print(f"  post_data: {str(pd)[:200]}...")
            except Exception:
                pass

if __name__ == "__main__":
    search_trace()
