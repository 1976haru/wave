# Music Wave Studio memory monitor (v0.8.5.4).
# Writes a locale-independent CSV: numbers use InvariantCulture "F1" (no
# thousands separators), and the app and FFmpeg are reported in separate
# columns instead of being summed into one row.
#
#   powershell -ExecutionPolicy Bypass -File tools\memory_watch.ps1 -Output MWS_MEMORY_WATCH.csv
param(
    [string]$Output = "MWS_MEMORY_WATCH.csv",
    [string]$ProcessName = "MusicWaveStudio*",
    [int]$AppPid = 0,
    [int]$IntervalSeconds = 5,
    [int]$DurationMinutes = 0
)
$ErrorActionPreference = "SilentlyContinue"
$inv = [System.Globalization.CultureInfo]::InvariantCulture
function Mb([double]$bytes) { return [string]::Format($inv, "{0:F1}", $bytes / 1MB) }
$header = "Time,AppPid,AppCount,WorkingSetMB,PrivateMB,PeakWorkingSetMB,Handles,Threads,FfmpegCount,FfmpegWorkingSetMB,FfmpegPrivateMB,AvailableMB"
[System.IO.File]::WriteAllText($Output, $header + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
$deadline = if ($DurationMinutes -gt 0) { (Get-Date).AddMinutes($DurationMinutes) } else { [DateTime]::MaxValue }
while ((Get-Date) -lt $deadline) {
    if ($AppPid -gt 0) { $apps = @(Get-Process -Id $AppPid) } else { $apps = @(Get-Process -Name $ProcessName) }
    $apps = @($apps | Where-Object { $_ })
    $appIds = @($apps | ForEach-Object { $_.Id })
    $ffmpeg = @(Get-CimInstance Win32_Process -Filter "Name='ffmpeg.exe'" | Where-Object { $appIds -contains [int]$_.ParentProcessId } | ForEach-Object { Get-Process -Id $_.ProcessId } | Where-Object { $_ })
    $ws = ($apps | Measure-Object WorkingSet64 -Sum).Sum
    $pm = ($apps | Measure-Object PrivateMemorySize64 -Sum).Sum
    $peak = ($apps | Measure-Object PeakWorkingSet64 -Maximum).Maximum
    $handles = ($apps | Measure-Object HandleCount -Sum).Sum
    $threads = 0; foreach ($p in $apps) { $threads += $p.Threads.Count }
    $fws = ($ffmpeg | Measure-Object WorkingSet64 -Sum).Sum
    $fpm = ($ffmpeg | Measure-Object PrivateMemorySize64 -Sum).Sum
    $avail = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
    $row = @(
        (Get-Date).ToString("yyyy-MM-dd HH:mm:ss", $inv),
        ($appIds -join ";"), $apps.Count, (Mb $ws), (Mb $pm), (Mb $peak),
        [string]::Format($inv, "{0:D}", [int64]$handles), [string]::Format($inv, "{0:D}", [int64]$threads),
        $ffmpeg.Count, (Mb $fws), (Mb $fpm), (Mb $avail)
    ) -join ","
    [System.IO.File]::AppendAllText($Output, $row + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
    if ($AppPid -gt 0 -and $apps.Count -eq 0) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
