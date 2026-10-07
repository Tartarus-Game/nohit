$url = 'http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1&candidate=1f39f386fd48e11e2b1127affd7cf8ef78b1041a3ffdabe393c3974c078ab692'
$chromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$args = @(
    '--remote-debugging-port=9222',
    '--remote-allow-origins=*',
    '--window-size=1280,800',
    '--window-position=50,50',
    $url
)

Write-Host "Launching Chrome to: $url"
Start-Process -FilePath $chromePath -ArgumentList $args
Start-Sleep -Seconds 2
Get-Process chrome -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, MainWindowTitle, MainWindowHandle
