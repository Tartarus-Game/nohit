param(
    [Parameter(Mandatory=$true)][string]$Round,
    [int]$Width = 1200,
    [int]$Seconds = 2400,
    [int]$Bindings = 1,
    [string]$Tag = "long",
    [string]$Base = "C:\Users\lf\Documents\Workspace\nohit",
    [string]$Http = "http://127.0.0.1:8160"
)
$ErrorActionPreference = "Stop"
$ent = Join-Path $Base "scratch\haoge-run\entries\$Round.request.json"
$req = Get-Content $ent -Raw | ConvertFrom-Json
$req.width = $Width; $req.seconds = $Seconds; $req.max_ticks = 40000; $req.max_bindings = $Bindings
$req.request_id = [guid]::NewGuid().ToString(); $req.progress_id = $req.request_id
$body = Join-Path $Base "scratch\haoge-run\_$Round.$Tag.body.json"
$req | ConvertTo-Json -Depth 8 -Compress | Set-Content $body -Encoding UTF8
$started = Get-Date
try {
    $resp = Invoke-WebRequest -Uri "$Http/api/solve-csv" -Method POST -InFile $body `
        -ContentType 'application/json' -UseBasicParsing -TimeoutSec ($Seconds + 600)
    $out = Join-Path $Base "scratch\haoge-run\routes\$Round.$Tag.json"
    $resp.Content | Set-Content $out -Encoding UTF8
    $j = $resp.Content | ConvertFrom-Json
    $actions = if ($j.actions) { $j.actions.Count } else { 0 }
    $line = "{0,-24} {1,-16} a={2} reached={3} reason={4} wall={5}s" -f `
        $Round, $j.status, $actions, $j.reached_tick, $j.reason, [math]::Round(((Get-Date) - $started).TotalSeconds)
} catch {
    $line = "{0,-24} ERROR {1}" -f $Round, $_.Exception.Message
}
Remove-Item $body -Force -ErrorAction SilentlyContinue
$line | Tee-Object -FilePath (Join-Path $Base "scratch\haoge-run\long-$Round.log")
