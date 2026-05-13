' reiniciar.vbs - detiene la app y la vuelve a arrancar (sin ventana ni clics).
' Doble clic para reiniciar el servidor Flask completo.
Set WshShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

' 1. Detener (modo silencioso, sin MsgBox). True = esperar a que termine.
WshShell.Run "wscript.exe """ & strPath & "\detener.vbs"" /silent", 0, True

' 2. Esperar 2 segundos a que los procesos se liberen del puerto 8000.
WScript.Sleep 2000

' 3. Iniciar de nuevo. False = no esperar (queda corriendo en background).
WshShell.Run "wscript.exe """ & strPath & "\iniciar.vbs""", 0, False
