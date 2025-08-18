' run_ps.vbs - 더블클릭하면 ps1을 창 없이 실행
Option Explicit
Dim shell, scriptPath, args, i, quotedArgs
Set shell = CreateObject("WScript.Shell")

' 실행할 ps1 경로 (필요에 맞게 변경)
scriptPath = ".\psrun.ps1"

' 더블클릭한 vbs에 넘긴 인자들을 ps1에도 그대로 전달
quotedArgs = ""
If WScript.Arguments.Count > 0 Then
  For i = 0 To WScript.Arguments.Count - 1
    quotedArgs = quotedArgs & " " & Chr(34) & WScript.Arguments(i) & Chr(34)
  Next
End If

' 창 숨김(0), 종료 대기(True/False 선택)
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & _
          Chr(34) & scriptPath & Chr(34) & quotedArgs, 0, True

