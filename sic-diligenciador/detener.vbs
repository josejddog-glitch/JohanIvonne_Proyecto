' detener.vbs - mata el servidor Flask local (procesos python.exe sirviendo la app).
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "taskkill /F /IM python.exe", 0, True
MsgBox "Servidor detenido.", 64, "SIC Diligenciador"
