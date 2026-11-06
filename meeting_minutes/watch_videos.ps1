# Watch Videos Folder for New Recordings
# Automatically triggers the meeting minutes workflow when a new video/audio file appears.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\stevekxs\Documents\Meeting Notes\meeting_minutes\watch_videos.ps1"
#
# To run at startup, create a shortcut in shell:startup pointing to this script.

$watchPath = "C:\Users\stevekxs\Videos"
$scriptPath = "C:\Users\stevekxs\Documents\Meeting Notes\meeting_minutes\transcribe_and_summarize.py"
$outputDir = "C:\Users\stevekxs\Documents\Meeting Notes\meeting_minutes\output"

# Supported file extensions
$extensions = @("*.mp4", "*.mp3", "*.wav", "*.m4a", "*.webm", "*.ogg", "*.flac", "*.avi", "*.mkv", "*.wma")

# Ensure output directory exists
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# Refresh PATH to include ffmpeg
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MEETING MINUTES - FILE WATCHER" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Watching: $watchPath" -ForegroundColor White
Write-Host "  Output:   $outputDir" -ForegroundColor White
Write-Host "  Extensions: $($extensions -join ', ')" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Waiting for new recordings..." -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

# Create FileSystemWatcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $watchPath
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName

# Track processed files to avoid duplicates
$processed = @{}

# Event handler for new files
$action = {
    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = $Event.SourceEventArgs.Name
    $ext = [System.IO.Path]::GetExtension($fileName).ToLower()

    # Check if extension matches
    $validExts = @(".mp4", ".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac", ".avi", ".mkv", ".wma")
    if ($ext -notin $validExts) { return }

    # Skip if already processed
    if ($processed.ContainsKey($filePath)) { return }
    $processed[$filePath] = $true

    Write-Host ""
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] New recording detected: $fileName" -ForegroundColor Yellow

    # Wait for file to finish writing (check if file is still growing)
    Start-Sleep -Seconds 5
    $lastSize = -1
    $currentSize = (Get-Item $filePath).Length
    while ($currentSize -ne $lastSize) {
        $lastSize = $currentSize
        Start-Sleep -Seconds 3
        $currentSize = (Get-Item $filePath -ErrorAction SilentlyContinue).Length
    }

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] File ready. Starting transcription workflow..." -ForegroundColor Green

    # Run the meeting minutes script
    $outputName = [System.IO.Path]::GetFileNameWithoutExtension($fileName)
    $cmd = "python `"$using:scriptPath`" `"$filePath`" --output `"$outputName`" --output-dir `"$using:outputDir`""

    try {
        Invoke-Expression $cmd
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Done! Meeting minutes saved to: $using:outputDir" -ForegroundColor Green
    }
    catch {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERROR: $_" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "  Waiting for new recordings..." -ForegroundColor Green
}

# Register the event
Register-ObjectEvent $watcher "Created" -Action $action | Out-Null
Register-ObjectEvent $watcher "Renamed" -Action $action | Out-Null

# Keep script running
try {
    while ($true) { Start-Sleep -Seconds 1 }
}
finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Write-Host "Watcher stopped." -ForegroundColor Gray
}
