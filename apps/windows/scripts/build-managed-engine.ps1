param([string]$GoExecutable = 'go', [string]$WintunArchive = '')
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$engineSource = Join-Path $repository 'engines/managed'
$output = Join-Path $repository 'apps/windows/src-tauri/engine'
New-Item -ItemType Directory -Force -Path $output | Out-Null
if (!$WintunArchive) {
    $WintunArchive = Join-Path $output 'wintun-0.14.1.zip'
    Invoke-WebRequest -Uri 'https://www.wintun.net/builds/wintun-0.14.1.zip' -OutFile $WintunArchive -TimeoutSec 60
}
$WintunArchive = (Resolve-Path -LiteralPath $WintunArchive).Path
$expected = '07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51'
if ((Get-FileHash -LiteralPath $WintunArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Wintun distribution checksum mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($WintunArchive)
try {
    foreach ($entry in @(@('wintun/bin/amd64/wintun.dll', 'wintun.dll'), @('wintun/LICENSE.txt', 'Wintun-Prebuilt-License.txt'))) {
        $item = $archive.GetEntry($entry[0])
        if (!$item) { throw 'Missing pinned Wintun distribution entry' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($item, (Join-Path $output $entry[1]), $true)
    }
} finally { $archive.Dispose() }
if ((Get-AuthenticodeSignature (Join-Path $output 'wintun.dll')).Status -ne 'Valid') { throw 'Wintun signature is not valid' }
Push-Location $engineSource
try {
    & $GoExecutable build -trimpath -ldflags=-checklinkname=0 -o (Join-Path $output 'pl-engine.exe') ./cmd/pl-engine
    if ($LASTEXITCODE -ne 0) { throw 'Managed engine build failed' }
    @{ engine_sha256 = (Get-FileHash (Join-Path $output 'pl-engine.exe') -Algorithm SHA256).Hash.ToLowerInvariant(); wintun_archive_sha256 = $expected; source_sha = (& git -C $repository rev-parse HEAD) } |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $output 'identity.json')
    if ($env:GITHUB_ACTIONS -eq 'true') {
        & $GoExecutable install github.com/google/go-licenses/v2@v2.0.1
        if ($LASTEXITCODE -ne 0) { throw 'License tool setup failed' }
        & go-licenses check ./cmd/pl-engine --allowed_licenses=MIT,MPL-2.0,Apache-2.0,BSD-2-Clause,BSD-3-Clause,ISC
        if ($LASTEXITCODE -ne 0) { throw 'Managed dependency license audit failed' }
        # Keep corresponding sources outside the app: test discovery must not
        # execute the archived copy of the frontend test suite.
        $distribution = Join-Path $env:RUNNER_TEMP ('prettylisa-managed-source-' + [guid]::NewGuid())
        $sources = Join-Path $distribution 'source'
        New-Item -ItemType Directory -Force -Path $sources | Out-Null
        $sourceTar = Join-Path $distribution 'source.tar'
        & git -C $repository archive --output $sourceTar HEAD engines/managed apps/windows
        if ($LASTEXITCODE -ne 0) { throw 'Source archive failed' }
        & tar -xf $sourceTar -C $sources
        if ($LASTEXITCODE -ne 0) { throw 'Source extraction failed' }
        & $GoExecutable mod vendor -o (Join-Path $sources 'engines/managed/vendor')
        if ($LASTEXITCODE -ne 0) { throw 'Corresponding dependency sources missing' }
        $notices = Join-Path $distribution 'licenses'
        & go-licenses save ./cmd/pl-engine --save_path $notices
        if ($LASTEXITCODE -ne 0) { throw 'Dependency notices missing' }
        Copy-Item (Join-Path $output 'Wintun-Prebuilt-License.txt'), (Join-Path $output 'identity.json') $distribution
        & tar -czf (Join-Path $output 'managed-source.tar.gz') -C $distribution source licenses Wintun-Prebuilt-License.txt identity.json
        if ($LASTEXITCODE -ne 0) { throw 'Corresponding source package failed' }
    }
} finally { Pop-Location }
