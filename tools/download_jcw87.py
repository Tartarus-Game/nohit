import urllib.request
import json
import os
from pathlib import Path

target_dir = Path("jcw87-c2-sans-fight")
target_dir.mkdir(exist_ok=True)
(target_dir / "images").mkdir(exist_ok=True)
(target_dir / "media").mkdir(exist_ok=True)

base_api = 'https://api.github.com/repos/Jcw87/c2-sans-fight/contents/'

def get_items(path=""):
    url = f"{base_api}{path}?ref=gh-pages"
    req = urllib.request.Request(url, headers={'User-Agent': 'Python'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

print("Fetching root files list...")
root_items = get_items("")
print(f"Root items: {len(root_items)}")

download_queue = []

for item in root_items:
    if item['type'] == 'file':
        download_queue.append((item['path'], target_dir / item['name'], item['size']))
    elif item['type'] == 'dir':
        print(f"Fetching {item['name']} list...")
        sub_items = get_items(item['path'])
        for s in sub_items:
            download_queue.append((s['path'], target_dir / item['name'] / s['name'], s['size']))

print(f"Total files to download: {len(download_queue)}")

success_count = 0
failed = []

for rel_path, dest_path, expected_size in download_queue:
    # Use jcw87.github.io as primary fast CDN, raw.githubusercontent as fallback
    cdn_url = f"https://jcw87.github.io/c2-sans-fight/{rel_path}"
    raw_url = f"https://raw.githubusercontent.com/Jcw87/c2-sans-fight/gh-pages/{rel_path}"
    
    downloaded = False
    for url in (cdn_url, raw_url):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
                dest_path.write_bytes(content)
                success_count += 1
                downloaded = True
                break
        except Exception as e:
            continue
    if not downloaded:
        print(f"FAILED to download: {rel_path}")
        failed.append(rel_path)

print(f"Download complete: {success_count}/{len(download_queue)} files downloaded.")
if failed:
    print("Failed files:", failed)
