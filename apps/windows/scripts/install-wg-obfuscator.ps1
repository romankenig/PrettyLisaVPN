param([string]$Destination = "$env:LOCALAPPDATA\PrettyLisaVPN\components\wg-obfuscator-1.6")
$ErrorActionPreference = 'Stop'
$digest = '2e940fcd137ad13e4ef881237c6ad5e08cb16de8415f5b2324ebca16393df04e'
$archive = Join-Path ([IO.Path]::GetTempPath()) ('plvpn-wgo-' + [guid]::NewGuid() + '.zip')
try {
    Invoke-WebRequest 'https://github.com/ClusterM/wg-obfuscator/releases/download/v1.6/wg-obfuscator-v1.6-windows-x64.zip' -OutFile $archive
    if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) { throw 'Archive hash mismatch' }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
    Get-ChildItem -LiteralPath $Destination -Recurse -File | Select-Object FullName
    Get-ChildItem -LiteralPath $Destination -Recurse -Filter wg-obfuscator.exe | Get-FileHash -Algorithm SHA256
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
}
