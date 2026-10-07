@echo off
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --enable-logging=stderr --v=1 http://127.0.0.1:8103/game/index.html?mode=single^&attack=sans_platforms4hard^&seed=42^&acceptance=1^&continuous=1^&candidate=1f39f386fd48e11e2b1127affd7cf8ef78b1041a3ffdabe393c3974c078ab692 > chrome.log 2>&1
