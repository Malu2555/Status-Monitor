# Registers a Windows Task Scheduler job that runs `manage.py run_checks` every minute.
# Requires elevated PowerShell:  powershell -ExecutionPolicy Bypass -File .\scripts\run_checks_scheduled.ps1

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$ManagePy = Join-Path $ProjectRoot 'backend\manage.py'
$Backend = Join-Path $ProjectRoot 'backend'

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$ManagePy`" run_checks" -WorkingDirectory $Backend
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName 'StatusMonitor-RunChecks' -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Run due Status Monitor checks every minute.' -Force

Write-Host 'Task registered: StatusMonitor-RunChecks (runs manage.py run_checks every minute).'
