param(
  [string]$TaskName = "MechatronicsJobIntelligenceDaily",
  [string]$Time = "07:30",
  [string]$RepoRoot = "",
  [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $PythonExe) {
  $PythonExe = (Get-Command python).Source
}

$scriptPath = Join-Path $RepoRoot "scripts\job_intelligence_update.py"
$sourcesPath = Join-Path $RepoRoot "knowledge\job_intelligence_sources.json"

if (-not (Test-Path $scriptPath)) {
  throw "Cannot find updater script: $scriptPath"
}
if (-not (Test-Path $sourcesPath)) {
  throw "Cannot find source config: $sourcesPath"
}

$runAt = [DateTime]::ParseExact($Time, "HH:mm", $null)
$arguments = "`"$scriptPath`" --sources `"$sourcesPath`""
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $arguments -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $runAt
$description = "Collect approved job intelligence and generate pending ability graph proposals for the mechatronics MVP."

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description $description -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName' to run daily at $Time."
Write-Host "Command: $PythonExe $arguments"
