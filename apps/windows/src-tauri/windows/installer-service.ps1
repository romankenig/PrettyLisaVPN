param([Parameter(Mandatory)][ValidateSet('prepare','remove')][string]$Action)
$ErrorActionPreference = 'Stop'
# Setup may be launched by PowerShell 7. Load only this Windows PowerShell's
# built-in modules, never inherited/user module paths in an elevated process.
$env:PSModulePath = Join-Path $PSHOME 'Modules'
# Fixed machine-wide location. Never use an environment-controlled executable path.
$target = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'PrettyLisaVPN'
function Assert-ProtectedPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse installation path rejected' }
    $acl = Get-Acl -LiteralPath $Path
    $trusted = @('S-1-5-18','S-1-5-32-544','S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'Untrusted installation owner' }
    # File/directory writes, deletion, DACL and owner changes.
    $write = 0x000D0156
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and ($rule.FileSystemRights.value__ -band $write) -and $rule.IdentityReference.Value -notin ($trusted + 'S-1-3-0')) { throw 'Writable installation path rejected' }
    }
}
Assert-ProtectedPath $target
Assert-ProtectedPath (Join-Path $target 'prettylisavpn-windows.exe')
Assert-ProtectedPath (Join-Path $target 'installer-service.ps1')
foreach ($name in @('PrettyLisaVPNService','WireGuardTunnel$PrettyLisaVPN')) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($null -eq $service) { continue }
    $record = Get-CimInstance Win32_Service -Filter "Name='$name'"
    $serviceProcess = if ($record.ProcessId) { Get-Process -Id $record.ProcessId -ErrorAction SilentlyContinue } else { $null }
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $name -ErrorAction Stop
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(40))
    }
    if ($serviceProcess -and -not $serviceProcess.WaitForExit(15000)) { throw 'VPN service did not exit' }
    & "$([Environment]::SystemDirectory)\sc.exe" delete $name | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'VPN service removal failed' }
    $service.Dispose()
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (Get-Service -Name $name -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'VPN service deletion is pending' }
        Start-Sleep -Milliseconds 100
    }
}
if ($Action -eq 'prepare' -and -not (Test-Path -LiteralPath $target)) {
    New-Item -ItemType Directory -Path $target | Out-Null
    Assert-ProtectedPath $target
}
exit 0
