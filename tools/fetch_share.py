import urllib.request

url = 'https://share.gemini.google/oedPMXbHcW5Q'
req = urllib.request.Request(
    url,
    headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
)

try:
    with urllib.request.urlopen(req) as resp:
        print("Final URL:", resp.geturl())
        print("Status:", resp.getcode())
        content = resp.read()
        print("Content length:", len(content))
        with open('tools/share_response.html', 'wb') as f:
            f.write(content)
        print("Saved to tools/share_response.html")
except Exception as e:
    print("Error:", e)
