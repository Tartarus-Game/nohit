import urllib.request
import json

req = urllib.request.Request('https://api.github.com/repos/Jcw87/c2-sans-fight/contents?ref=gh-pages', headers={'User-Agent': 'Python'})
files = json.loads(urllib.request.urlopen(req).read())
print(f"Total files on gh-pages: {len(files)}")
for f in files:
    print(f"{f['name']:30} {f['type']:6} {str(f.get('size')):10} {f.get('download_url')}")
