param(
    [Parameter(Mandatory = $true)][int]$AppProcessId,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [ValidateSet("Capture", "Maximize", "Restore", "Minimize", "Close")]
    [string]$Action = "Capture"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ReviewWindow {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr hwnd, int index);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hwnd, uint message, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    private delegate bool EnumCallback(IntPtr hwnd, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumCallback callback, IntPtr parameter);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, System.Text.StringBuilder text, int count);
    public static IntPtr FindApplicationWindow(int processId) {
        IntPtr result = IntPtr.Zero;
        EnumWindows((hwnd, parameter) => {
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            if (owner == processId) {
                var text = new System.Text.StringBuilder(256);
                GetWindowText(hwnd, text, text.Capacity);
                if (text.ToString() == "PrettyLisaVPN") {
                    result = hwnd;
                    return false;
                }
            }
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
'@
[ReviewWindow]::SetProcessDPIAware() | Out-Null
$handle = [IntPtr]::Zero
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $handle = [ReviewWindow]::FindApplicationWindow($AppProcessId)
    if ($handle -ne [IntPtr]::Zero) { break }
    Start-Sleep -Milliseconds 100
}
if ($handle -eq [IntPtr]::Zero) { throw "Native application window not found" }

$style = [ReviewWindow]::GetWindowLong($handle, -16)
if (($style -band 0x00020000) -eq 0 -or
    ($style -band 0x00010000) -eq 0 -or
    ($style -band 0x00080000) -eq 0) {
    throw "Expected native minimize, maximize and system menu controls"
}

switch ($Action) {
    "Maximize" {
        [ReviewWindow]::ShowWindow($handle, 3) | Out-Null
        Start-Sleep -Milliseconds 300
        if (-not [ReviewWindow]::IsZoomed($handle)) { throw "Maximize failed" }
    }
    "Restore" {
        [ReviewWindow]::ShowWindow($handle, 9) | Out-Null
        Start-Sleep -Milliseconds 300
        if ([ReviewWindow]::IsZoomed($handle) -or [ReviewWindow]::IsIconic($handle)) {
            throw "Restore failed"
        }
    }
    "Minimize" {
        [ReviewWindow]::ShowWindow($handle, 6) | Out-Null
        Start-Sleep -Milliseconds 300
        if (-not [ReviewWindow]::IsIconic($handle)) { throw "Minimize failed" }
    }
    "Close" {
        if (-not [ReviewWindow]::PostMessage($handle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)) {
            throw "Close request failed"
        }
        return
    }
}

if ($Action -eq "Minimize") { return }
$rect = New-Object ReviewWindow+RECT
if (-not [ReviewWindow]::GetWindowRect($handle, [ref]$rect)) { throw "GetWindowRect failed" }
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -lt 100 -or $height -lt 100) { throw "Invalid native window bounds" }
$bitmap = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $dc = $graphics.GetHdc()
    try {
        if (-not [ReviewWindow]::PrintWindow($handle, $dc, 2)) { throw "PrintWindow failed" }
    } finally {
        $graphics.ReleaseHdc($dc)
    }
    # Reject a blank capture; never replace native chrome with a drawn imitation.
    $colors = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($x = 10; $x -lt $width; $x += 31) {
        for ($y = 10; $y -lt $height; $y += 31) {
            $colors.Add($bitmap.GetPixel($x, $y).ToArgb()) | Out-Null
        }
    }
    if ($colors.Count -lt 8) { throw "Native capture is blank" }
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}
