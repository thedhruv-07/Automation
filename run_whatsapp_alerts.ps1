# run_whatsapp_alerts.ps1
Set-Location -Path $PSScriptRoot
& "C:\Python314\python.exe" "dashboard-app\backend\whatsapp_renewal_alerts.py" *>> "logs\scheduler_output.log"
