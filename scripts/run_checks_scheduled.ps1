# Registers Windows Task Scheduler jobs:
#   - StatusMonitor-RunChecks          every minute
#   - StatusMonitor-DeliverNotify      every minute
#   - StatusMonitor-CheckSsl           daily at 06:00
#   - StatusMonitor-CheckDomains       daily at 06:30
#   - StatusMonitor-CrawlLinks         daily at 07:00
# Requires elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\run_checks_scheduled.ps1

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$ManagePy = Join-Path $ProjectRoot 'backend\manage.py'
$Backend = Join-Path $ProjectRoot 'backend'

function Register-Job($Name, $Arguments, $Trigger, $Description) {
    $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$ManagePy`" $Arguments" -WorkingDirectory $Backend
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger -Settings $Settings -Description $Description -Force
    Write-Host "Task registered: $Name"
}

$EveryMinute = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1)
$DailyAt6 = New-ScheduledTaskTrigger -Daily -At '06:00'
$DailyAt630 = New-ScheduledTaskTrigger -Daily -At '06:30'
$DailyAt7 = New-ScheduledTaskTrigger -Daily -At '07:00'

Register-Job 'StatusMonitor-RunChecks' 'run_checks' $EveryMinute 'Run due Status Monitor checks every minute.'
Register-Job 'StatusMonitor-DeliverNotify' 'deliver_notifications' $EveryMinute 'Send queued Status Monitor notifications every minute.'
Register-Job 'StatusMonitor-CheckSsl' 'check_ssl' $DailyAt6 'Refresh TLS certificate expiry daily.'
Register-Job 'StatusMonitor-CheckDomains' 'check_domains' $DailyAt630 'Refresh domain registration expiry daily.'
Register-Job 'StatusMonitor-CrawlLinks' 'crawl_links' $DailyAt7 'Crawl broken-link monitors daily.'

Write-Host 'Done: 2 minute jobs + 3 daily sweeps (SSL, domains, broken links).'
