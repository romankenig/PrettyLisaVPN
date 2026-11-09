# Fixed native operation. No caller-provided paths, commands, passwords or scripts.
$ErrorActionPreference = 'Stop'
function Has-KasperskyRoute {
    $vpnAdapters = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match '^Kaspersky.*(VPN|Tunnel)' })
    $routes = @(Get-NetRoute -AddressFamily IPv4 | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0', '0.0.0.0/1', '128.0.0.0/1') -and $_.InterfaceIndex -in $vpnAdapters.ifIndex })
    return $routes.Count -gt 0
}
if (-not (Has-KasperskyRoute)) { exit 0 }
$roots = @([Environment]::GetFolderPath('ProgramFilesX86'), [Environment]::GetFolderPath('ProgramFiles')) | Select-Object -Unique
$candidates = @(
    foreach ($root in $roots) {
        $vendor = Join-Path $root 'Kaspersky Lab'
        if (Test-Path -LiteralPath $vendor) {
            Get-ChildItem -LiteralPath $vendor -Directory | Where-Object { $_.Name -match '^Kaspersky (Secure Connection|VPN) \d+(\.\d+)*$' } | ForEach-Object {
                $program = Join-Path $_.FullName 'avp.com'
                if (Test-Path -LiteralPath $program) {
                    $signature = Get-AuthenticodeSignature -LiteralPath $program
                    if ($signature.Status -eq 'Valid' -and $signature.SignerCertificate.Subject -match 'CN=(AO |JSC |ZAO )?Kaspersky Lab(,|$)') { $program }
                }
            }
        }
    }
)
if ($candidates.Count -ne 1) { exit 17 }
# EXIT is the installed VPN CLI's documented application exit. Never STOP Protection,
# disable an adapter/service, kill the VPN process, or invoke antivirus executables.
$process = Start-Process -FilePath $candidates[0] -ArgumentList 'EXIT' -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(10000)) { exit 17 }
if ($process.ExitCode -ne 0) { exit 17 }
$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    if (-not (Has-KasperskyRoute)) { exit 0 }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)
exit 17
