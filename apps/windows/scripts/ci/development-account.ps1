param([ValidateSet('create', 'cleanup')][string]$Mode)
$ErrorActionPreference = 'Stop'
$sshRoot = Join-Path $env:RUNNER_TEMP 'acceptance-ssh'
New-Item -ItemType Directory -Force $sshRoot | Out-Null
$key = Join-Path $sshRoot 'id_ed25519'
$known = Join-Path $sshRoot 'known_hosts'
try {
  [IO.File]::WriteAllText($key, $env:DEV_SSH_PRIVATE_KEY + "`n", [Text.UTF8Encoding]::new($false))
  [IO.File]::WriteAllText($known, $env:DEV_SSH_KNOWN_HOSTS + "`n", [Text.UTF8Encoding]::new($false))
  icacls $key /inheritance:r /grant:r "$($env:USERNAME):(R)" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'SSH key permissions failed' }
  if ($env:DEV_VPS_HOST -ne '95.140.152.42' -or $env:DEV_VPS_PORT -ne '22') { throw 'Unexpected development target' }
  $scope = "$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)"
  $script = Get-Content -Raw scripts/ci/development-account.py
  $remote = 'container=$(docker ps --filter label=com.docker.compose.project=prettylisavpn-development --filter label=com.docker.compose.service=backend --format "{{.ID}}"); test $(echo "$container" | wc -w) -eq 1 && docker exec -i "$container" python - ' + $Mode + ' ' + $scope
  $result = $script | ssh -i $key -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" -o ConnectTimeout=10 -o LogLevel=ERROR -p $env:DEV_VPS_PORT "$($env:DEV_VPS_USER)@$($env:DEV_VPS_HOST)" $remote
  if ($LASTEXITCODE -ne 0) { throw 'Development account operation failed' }
  $value = ($result -join "`n") | ConvertFrom-Json
  if ($Mode -eq 'create') {
    if (!$value.credential.refresh_token) { throw 'Missing disposable credential' }
    Write-Output "::add-mask::$($value.credential.refresh_token)"
    Write-Output "::add-mask::$($value.access_token)"
    [IO.File]::WriteAllText($env:ACCEPTANCE_CREDENTIAL_PATH, ($value | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
  } else {
    $value | ConvertTo-Json -Compress
    if (Test-Path $env:ACCEPTANCE_CREDENTIAL_PATH) { Remove-Item $env:ACCEPTANCE_CREDENTIAL_PATH -Force }
  }
} finally {
  Remove-Item $sshRoot -Recurse -Force -ErrorAction SilentlyContinue
}
