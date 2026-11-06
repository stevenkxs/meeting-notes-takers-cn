# Install the Meeting Minutes Watcher as a Windows Scheduled Task
# This makes it start automatically when you log in.
#
# Run this once (as Administrator is NOT required):
#   powershell -ExecutionPolicy Bypass -File "install_watcher.ps1"

$taskName = "MeetingMinutesWatcher"
$scriptPath = "C:\Users\stevekxs\Documents\Meeting Notes\meeting_minutes\watch_videos.ps1"

# Remove existing task if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Create the task action
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Trigger: at user logon
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

# Register the task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Watches C:\Users\stevekxs\Videos for new recordings and generates meeting minutes automatically."

Write-Host ""
Write-Host "Task '$taskName' registered successfully." -ForegroundColor Green
Write-Host "The watcher will start automatically at next login." -ForegroundColor White
Write-Host ""
Write-Host "To start it now without rebooting:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Cyan
Write-Host ""
Write-Host "To remove it later:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor Cyan
