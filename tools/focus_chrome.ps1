Add-Type @'
  using System;
  using System.Runtime.InteropServices;
  public class User32 {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  }
'@

$procs = Get-Process chrome -ErrorAction SilentlyContinue
foreach ($p in $procs) {
  if ($p.MainWindowHandle -ne [IntPtr]::Zero) {
    Write-Output "Focusing Chrome PID $($p.Id), Handle: $($p.MainWindowHandle)"
    [User32]::ShowWindow($p.MainWindowHandle, 9) | Out-Null # SW_RESTORE = 9
    [User32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
  }
}
