# PostgreSQL backup with simple daily rotation (Windows Task Scheduler).
# Uses standard libpq env vars or the app's DATABASE_URL directly.
$ErrorActionPreference = "Stop"

$BackupDir = $env:BACKUP_DIR
if (-not $BackupDir) { $BackupDir = "C:\Backups\statusmonitor" }
$KeepDaily = $env:KEEP_DAILY
if (-not $KeepDaily) { $KeepDaily = 7 }

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$output = Join-Path $BackupDir "statusmonitor-$stamp.dump"

if ($env:DATABASE_URL) {
    pg_dump --format=custom $env:DATABASE_URL --file=$output
} else {
    pg_dump --format=custom --file=$output
}

Write-Output "backup written: $output"
Get-ChildItem $BackupDir -Filter "statusmonitor-*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDaily) } |
    Remove-Item -Force
Write-Output "rotation done; keeping $KeepDaily daily file(s)"
