# Zero-Trust SOC — Windows Backup Scheduler
# Sets up a scheduled task to run the master backup script every 6 hours.

$TaskName = "ZeroTrustSOC_Backup"
$ActionScript = "C:\Program Files\Git\bin\bash.exe"
$ActionArgs = "-c 'cd C:/Users/adars/Documents/Coding/Project/Zero-Trust && bash infrastructure/backups/backup-all.sh'"
$ScheduleTime = (Get-Date).AddMinutes(5) # Start in 5 mins

Write-Host "[*] Creating Scheduled Task: $TaskName..."

$action = New-ScheduledTaskAction -Execute $ActionScript -Argument $ActionArgs
$trigger = New-ScheduledTaskTrigger -Daily -At $ScheduleTime.ToString("HH:mm")
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Repeat every 6 hours
$trigger.RepetitionInterval = (New-TimeSpan -Hours 6)
$trigger.RepetitionDuration = [TimeSpan]::MaxValue

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force

Write-Host "[+] Scheduled Task '$TaskName' registered successfully."
Write-Host "[!] Note: Task is set to run as SYSTEM for background execution."
