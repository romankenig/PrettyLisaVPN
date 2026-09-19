param(
    [Parameter(Mandatory)][string]$SshIdentity,
    [string]$Node = 'vpnadmin@204.48.17.50'
)
$ErrorActionPreference = 'Stop'
$identity = (Resolve-Path -LiteralPath $SshIdentity).Path
$directory = Join-Path $env:LOCALAPPDATA 'PrettyLisaVPN\wg-obfuscator'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $directory /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect key directory' }
$info = [Diagnostics.ProcessStartInfo]::new('ssh.exe')
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
foreach ($argument in @('-T', '-i', $identity, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', $Node, 'sudo -n cat /etc/prettylisavpn-wg-obfuscator/key.conf')) {
    $info.ArgumentList.Add($argument)
}
$process = [Diagnostics.Process]::Start($info)
$secret = $process.StandardOutput.ReadToEnd()
$null = $process.StandardError.ReadToEnd()
$process.WaitForExit()
try {
    if ($process.ExitCode -ne 0 -or $secret -cnotmatch '^key=[a-f0-9]{64}\s*$') { throw 'Key import failed; no secret printed' }
    $path = Join-Path $directory 'key.conf'
    if (-not (Test-Path -LiteralPath $path)) { New-Item -ItemType File -Path $path | Out-Null }
    & icacls.exe $path /inheritance:r /grant:r "*${sid}:F" '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot protect key file' }
    [IO.File]::WriteAllText($path, $secret, [Text.UTF8Encoding]::new($false))
    Write-Output "Imported obfuscation key into protected local file: $path"
} finally {
    $secret = $null
    $process.Dispose()
}
