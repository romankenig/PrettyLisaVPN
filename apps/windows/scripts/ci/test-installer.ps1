param([switch]$LeaveInstalled)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') { throw 'Isolated Windows CI runner required' }
$output = Join-Path (Get-Location) 'artifacts/installer-acceptance'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$setup = @(Get-ChildItem src-tauri/target/release/bundle/nsis/*-setup.exe)
if ($setup.Count -ne 1) { throw 'Expected one current installer' }
$directory = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'PrettyLisaVPN'
$executable = Join-Path $directory 'prettylisavpn-windows.exe'
$source = (Resolve-Path src-tauri/target/release/prettylisavpn-windows.exe).Path
$report = [ordered]@{ source_sha=$env:GITHUB_SHA; run_id=$env:GITHUB_RUN_ID; run_attempt=$env:GITHUB_RUN_ATTEMPT; checks=@() }
function Check([string]$Name, [bool]$Passed) {
    $report.checks += @{ name=$Name; passed=$Passed }
    $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $output 'proof.json')
    if (-not $Passed) { throw "Installer acceptance failed: $Name" }
}
function Run([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    $null = $process.Handle # Retain the native handle until ExitCode has been read.
    if (-not $process.WaitForExit(120000)) { throw 'Installer timeout' }
    Write-Output "Installer command exit code: $($process.ExitCode)"
    if ($process.ExitCode -ne 0) {
        Get-ChildItem -LiteralPath $directory -ErrorAction SilentlyContinue | Select-Object Name,Length
        Get-CimInstance Win32_Service -Filter "Name='PrettyLisaVPNService'" | Select-Object State,StartName,PathName,ExitCode
        foreach ($name in @('install-status.txt','installer-service.ps1','prettylisavpn-windows.exe')) {
            $path = Join-Path $directory $name
            if (Test-Path -LiteralPath $path) {
                if ($name -eq 'install-status.txt') { Get-Content -LiteralPath $path }
                else { Get-Acl -LiteralPath $path | Select-Object Owner,Sddl }
            }
        }
        if (Test-Path -LiteralPath $directory) { Get-Acl -LiteralPath $directory | Select-Object Owner,Sddl }
    }
    Check 'installer command completed' ($process.ExitCode -eq 0)
}
function Assert-Installed {
    $service = Get-CimInstance Win32_Service -Filter "Name='PrettyLisaVPNService'"
    Check 'automatic LocalSystem service is running' ($service.State -eq 'Running' -and $service.StartName -eq 'LocalSystem' -and $service.StartMode -eq 'Auto')
    Check 'installed bytes match current build' ((Get-FileHash -LiteralPath $source).Hash -eq (Get-FileHash -LiteralPath $executable).Hash)
    Check 'service uses quoted protected executable' ($service.PathName -eq ('"' + $executable + '" --vpn-service'))
    Run $executable @('--service-check')
}
Run $setup[0].FullName @('/S')
Assert-Installed
# A new standard account must be able to use the service without an administrator
# token or UAC prompt. Credentials stay only in memory on this disposable runner.
$username = 'pl-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$password = ConvertTo-SecureString ('Aa1!' + [guid]::NewGuid().ToString('N')) -AsPlainText -Force
$user = New-LocalUser -Name $username -Password $password -AccountNeverExpires
$credential = [pscredential]::new("$env:COMPUTERNAME\$username", $password)
try {
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $username
    Check 'test account is not an administrator' (-not ((Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value -contains $user.SID.Value))
    Start-Sleep -Seconds 2
    $client = Start-Process -FilePath $executable -ArgumentList '--service-check' -Credential $credential -LoadUserProfile -WorkingDirectory $directory -WindowStyle Hidden -PassThru
    $null = $client.Handle
    Check 'standard user IPC completes without UAC' ($client.WaitForExit(30000))
    Check 'standard user receives engine DOWN' ($client.ExitCode -eq 0)
    Start-Sleep -Seconds 2
    # Identical bytes outside the protected installation are not authorized.
    $foreign = Start-Process -FilePath $source -ArgumentList '--service-check' -WindowStyle Hidden -PassThru
    $null = $foreign.Handle
    Check 'uninstalled client is rejected promptly' ($foreign.WaitForExit(15000))
    Check 'uninstalled client cannot control privileged service' ($foreign.ExitCode -ne 0)
} finally { Remove-LocalUser -Name $username }
Start-Sleep -Seconds 2
Run $setup[0].FullName @('/S')
Assert-Installed
Check 'repair replaced service successfully' $true
Run (Join-Path $directory 'uninstall.exe') @('/S')
$deadline = [DateTime]::UtcNow.AddSeconds(20)
while ((Test-Path -LiteralPath $executable) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
Check 'uninstall removed service' ($null -eq (Get-Service PrettyLisaVPNService -ErrorAction SilentlyContinue))
Check 'uninstall removed application' (-not (Test-Path -LiteralPath $executable))
Check 'uninstall left no engine process' ($null -eq (Get-Process pl-engine -ErrorAction SilentlyContinue))
if ($LeaveInstalled) { Run $setup[0].FullName @('/S'); Assert-Installed }
