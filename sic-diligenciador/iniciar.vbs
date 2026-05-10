' iniciar.vbs - lanza la app sin mostrar ventana de consola.
' Doble-clic para arrancar. Para detener: Ctrl+Shift+Esc -> matar python.exe.
Set WshShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
' 0 = ventana oculta; False = no esperar a que termine
WshShell.Run """python.exe"" app.py", 0, False
WScript.Sleep 2500
WshShell.Run "http://localhost:8000", 1, False
