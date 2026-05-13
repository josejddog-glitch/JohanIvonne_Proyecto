' detener.vbs - mata el servidor Flask local (procesos python.exe sirviendo la app).
' Uso normal: doble clic.
' Uso silencioso (desde reiniciar.vbs): wscript detener.vbs /silent
silencio = False
For Each arg In WScript.Arguments
  If LCase(arg) = "/silent" Or LCase(arg) = "-silent" Then silencio = True
Next

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "taskkill /F /IM python.exe", 0, True

If Not silencio Then
  MsgBox "Servidor detenido.", 64, "SIC Diligenciador"
End If
