import json
import os

trace_file = r"e:\AILearn\20260321codexconsole\codex-console\data\universal_trace.jsonl"
output_file = "all_urls.txt"

def extract_urls():
    if not os.path.exists(trace_file):
        print(f"File not found: {trace_file}")
        return

    with open(trace_file, 'r', encoding='utf-8', errors='ignore') as f, open(output_file, 'w', encoding='utf-8') as out:
        for i, line in enumerate(f, 1):
            try:
                data = json.loads(line)
                url = data.get('url', '')
                method = data.get('method', 'RESP')
                if url:
                    out.write(f"Line {i}: {method} {url}\n")
            except:
                pass

if __name__ == "__main__":
    extract_urls()
    print("URLs extracted to all_urls.txt")
