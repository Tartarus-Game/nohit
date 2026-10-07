import json
import sys

file_path = r'<user>\.codex\sessions\2026\10\05\rollout-2026-10-05T00-15-29-01a107b2-edc3-7a32-8df1-89889b04c024.jsonl'
output_path = r'tools\codex_session_summary.txt'

lines_data = []
with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    for line_idx, line in enumerate(f):
        try:
            d = json.loads(line)
            lines_data.append((line_idx, d))
        except Exception as e:
            pass

out = []
out.append(f"Total JSONL lines: {len(lines_data)}")

# Extract turns
turns = []
for idx, d in lines_data:
    t = d.get('type')
    payload = d.get('payload', {})
    if t == 'response_item':
        role = payload.get('role')
        content = payload.get('content')
        item_type = payload.get('type')
        if role == 'user':
            text_blocks = []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get('type') == 'input_text':
                        text_blocks.append(b.get('text', ''))
            elif isinstance(content, str):
                text_blocks.append(content)
            full_text = "\n".join(text_blocks).strip()
            if full_text and not full_text.startswith("<in-app-browser-context") and not full_text.startswith("<external_codex_apps_open_page>"):
                out.append(f"\n--- [USER @ line {idx}] ---")
                out.append(full_text[:1500])
        elif role == 'assistant':
            text_blocks = []
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get('type') == 'text':
                        text_blocks.append(b.get('text', ''))
                    elif isinstance(b, str):
                        text_blocks.append(b)
            elif isinstance(content, str):
                text_blocks.append(content)
            full_text = "\n".join(text_blocks).strip()
            if full_text:
                out.append(f"\n--- [ASSISTANT @ line {idx}] ---")
                out.append(full_text[:1000] + ("..." if len(full_text) > 1000 else ""))
        elif item_type in ('function_call', 'tool_call', 'custom_tool_call'):
            name = payload.get('name') or payload.get('tool_name')
            args = payload.get('arguments') or payload.get('args')
            # Summarize important tool calls (e.g. bash commands, file edits)
            if name in ('bash', 'execute_command', 'write_file', 'edit_file', 'view_file', 'run_command'):
                out.append(f"[TOOL {name} @ line {idx}]: {str(args)[:200]}")

with open(output_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(out))

print(f"Summary written to {output_path}")
