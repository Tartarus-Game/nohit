Add-Type @'
  using System;
  using System.Runtime.InteropServices;
  using System.Text;
  public class User32 {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
  }
'@

[User32]::EnumWindows({
  param([IntPtr]$hWnd, [IntPtr]$lParam)
  if ([User32]::IsWindowVisible($hWnd)) {
    $sb = New-Object System.Text.StringBuilder 256
    [User32]::GetWindowText($hWnd, $sb, 256) | Out-Null
    $title = $sb.ToString()
    if ($title.Length -gt 0) {
      $pidOut = 0
      [User32]::GetWindowThreadProcessId($hWnd, [ref]$pidOut) | Out-Null
      $p = Get-Process -Id $pidOut -ErrorAction SilentlyContinue
      if ($p -and $p.ProcessName -like '*chrome*') {
        Write-Output "PID: $pidOut | Title: $title"
      }
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
