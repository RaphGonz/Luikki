@echo off
rem Arrete le serveur Luikki (celui qui ecoute sur le port).
rem   luikki-stop.bat                        -> port 8000
rem   set LUIKKI_PORT=8080 && luikki-stop.bat

setlocal
if "%LUIKKI_PORT%"=="" set LUIKKI_PORT=8000

powershell -NoProfile -Command ^
 "$p = Get-NetTCPConnection -LocalPort %LUIKKI_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -Expand OwningProcess -Unique;" ^
 "if (-not $p) { Write-Host 'Rien n''ecoute sur le port %LUIKKI_PORT%.'; exit 0 };" ^
 "$p | %%{ Stop-Process -Id $_ -Force; Write-Host \"Luikki arrete (PID $_).\" }"

endlocal
