param([ValidateSet('NONE','STUN')][string]$Masking = 'NONE')
$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent (Split-Path -Parent $app)
$exe = Join-Path $repo '.tools\wg-obfuscator-1.6\wg-obfuscator\wg-obfuscator.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    $exe = Join-Path $env:LOCALAPPDATA 'PrettyLisaVPN\components\wg-obfuscator-1.6\wg-obfuscator\wg-obfuscator.exe'
}
$key = Join-Path $env:LOCALAPPDATA 'PrettyLisaVPN\wg-obfuscator\key.conf'
if (-not (Test-Path -LiteralPath $exe) -or -not (Test-Path -LiteralPath $key)) {
    throw 'Install the pinned component and import its protected key first. See docs/wg-obfuscator.md.'
}
$env:PRETTYLISA_VPN_TRANSPORT_MODE = 'WG_OBFUSCATOR'
$env:PRETTYLISA_WG_OBFUSCATOR_EXE = $exe
$env:PRETTYLISA_WG_OBFUSCATOR_KEY_FILE = $key
$env:PRETTYLISA_WG_OBFUSCATOR_PORT = '443'
$env:PRETTYLISA_WG_OBFUSCATOR_MASKING = $Masking
$env:PRETTYLISA_VPN_DEBUG = '1'
Push-Location $app
try {
    pnpm tauri dev 2>&1 | Tee-Object -FilePath (Join-Path $env:TEMP 'prettylisavpn-wg-obfuscator-debug.log')
} finally { Pop-Location }
