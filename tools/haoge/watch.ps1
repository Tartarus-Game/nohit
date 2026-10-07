param(
    [int]$PollSeconds = 30,
    [int]$MaxMinutes = 60,
    [string]$Base = "C:\Users\lf\Documents\Workspace\nohit"
)
# Watch every solver result log; whenever one lands, re-emit the route index and
# append a status line. Runs in the background so the caller is never blocked.
$deadline = (Get-Date).AddMinutes($MaxMinutes)
$seen = @{}
$statusFile = Join-Path $Base "scratch\haoge-run\watch-status.txt"
while ((Get-Date) -lt $deadline) {
    $logs = Get-ChildItem (Join-Path $Base "scratch\haoge-run\proc-*.log") -ErrorAction SilentlyContinue
    $pending = 0
    foreach ($log in $logs) {
        $content = (Get-Content $log.FullName -Raw -ErrorAction SilentlyContinue)
        if (-not $content) { $pending++; continue }
        $line = $content.Trim().Split("`n")[0]
        if (-not $seen.ContainsKey($log.Name) -or $seen[$log.Name] -ne $line) {
            $seen[$log.Name] = $line
            $stamp = Get-Date -Format "HH:mm:ss"
            "$stamp  $($log.Name)  $line" | Add-Content $statusFile
        }
    }
    $running = (Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'solve_entry' } | Measure-Object).Count
    node (Join-Path $Base "scratch\haoge-run\emit_routes.mjs") --dir scratch/haoge-run --out ROUTES.json 2>&1 |
        Select-Object -Last 2 | ForEach-Object { "$(Get-Date -Format 'HH:mm:ss')  $($_)" | Add-Content $statusFile }
    if ($running -eq 0 -and $pending -eq 0) {
        "$(Get-Date -Format 'HH:mm:ss')  all solvers finished" | Add-Content $statusFile
        break
    }
    Start-Sleep -Seconds $PollSeconds
}
