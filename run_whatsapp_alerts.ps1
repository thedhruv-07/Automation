# run_whatsapp_alerts.ps1
Set-Location -Path $PSScriptRoot
& "C:\Python314\python.exe" "whatsapp_renewal_alerts.py" *>> "scheduler_output.log"
