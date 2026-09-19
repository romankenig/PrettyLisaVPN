# Run with both powershell.exe and pwsh.exe. Never starts Tauri or networking.
$ErrorActionPreference = 'Stop'
$launcher = Join-Path (Split-Path -Parent $PSScriptRoot) 'dev-wg-obfuscator.ps1'
$originalPath = $env:PATH
$originalTemp = $env:TEMP
$originalLocal = $env:LOCALAPPDATA
$originalTestExit = $env:PRETTYLISA_TEST_EXIT_CODE
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('plvpn-launcher-test-' + [guid]::NewGuid())
$variables = @('PRETTYLISA_VPN_TRANSPORT_MODE','PRETTYLISA_WG_OBFUSCATOR_EXE','PRETTYLISA_WG_OBFUSCATOR_KEY_FILE','PRETTYLISA_WG_OBFUSCATOR_PORT','PRETTYLISA_WG_OBFUSCATOR_MASKING','PRETTYLISA_VPN_DEBUG')
$saved = @{}
foreach ($name in $variables) { $saved[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    $env:TEMP = $testRoot
    $env:LOCALAPPDATA = $testRoot
    $env:PATH = (Join-Path $PSScriptRoot 'fixtures') + ';' + $originalPath
    New-Item -ItemType Directory -Path "$testRoot\PrettyLisaVPN\wg-obfuscator" -Force | Out-Null
    New-Item -ItemType Directory -Path "$testRoot\PrettyLisaVPN\components\wg-obfuscator-1.6\wg-obfuscator" -Force | Out-Null
    New-Item -ItemType File -Path "$testRoot\PrettyLisaVPN\wg-obfuscator\key.conf" | Out-Null
    New-Item -ItemType File -Path "$testRoot\PrettyLisaVPN\components\wg-obfuscator-1.6\wg-obfuscator\wg-obfuscator.exe" | Out-Null
    $locationBefore = (Get-Location).Path
    foreach ($code in @(0, 7)) {
        $env:PRETTYLISA_TEST_EXIT_CODE = [string]$code
        $failure = $null
        try { & $launcher -Masking NONE | Out-Null } catch { $failure = $_ }
        if ($code -eq 0 -and $failure) { throw $failure }
        if ($code -ne 0 -and (!$failure -or $failure.ToString() -notmatch 'exited with code 7')) {
            throw 'Nonzero native exit code was not reported correctly'
        }
        $log = Get-Content (Join-Path $testRoot 'prettylisavpn-wg-obfuscator-debug.log') -Raw
        if ($log -notmatch 'test-stdout' -or $log -notmatch 'test-stderr') { throw 'Missing stdout/stderr in log' }
        if ((Get-Location).Path -ne $locationBefore) { throw 'Launcher did not restore working directory' }
    }
    Write-Output "PASS: PowerShell $($PSVersionTable.PSVersion), stdout/stderr, exit 0/7, working directory"
} finally {
    $env:PATH = $originalPath
    $env:TEMP = $originalTemp
    $env:LOCALAPPDATA = $originalLocal
    $env:PRETTYLISA_TEST_EXIT_CODE = $originalTestExit
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $saved[$name]) }
    # Only our freshly generated, absolute temporary directory is eligible for cleanup.
    if ([IO.Path]::IsPathRooted($testRoot) -and (Split-Path -Leaf $testRoot) -like 'plvpn-launcher-test-*') {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
