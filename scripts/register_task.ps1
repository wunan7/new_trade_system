# Register daily paper trading task in Windows Task Scheduler
# Run as Administrator

$taskName = "DailyPaperTrading"
$scriptPath = "C:\Users\wunan\projects\new_solution\scripts\daily_task.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At 19:30
$action = New-ScheduledTaskAction -Execute $scriptPath
$settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Settings $settings -Force

Write-Host "Task '$taskName' registered to run daily at 19:30"
Write-Host "To verify: Get-ScheduledTask -TaskName $taskName"
