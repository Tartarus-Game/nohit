import urllib.request
import json

base_api = 'https://api.github.com/repos/Jcw87/c2-sans-fight/contents/'
for folder in ('images', 'media'):
    req = urllib.request.Request(f'{base_api}{folder}?ref=gh-pages', headers={'User-Agent': 'Python'})
    try:
        data = json.loads(urllib.request.urlopen(req).read())
        print(f"Directory {folder}: {len(data)} items")
        print("Sample:", [x['name'] for x in data[:10]])
    except Exception as e:
        print(f"Error {folder}: {e}")
