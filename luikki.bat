@echo off
rem Lance le serveur Luikki et ouvre l'appli dans le navigateur.
rem   luikki.bat                        -> port 8000, Cobra sur Modal (proposer remote)
rem   luikki.bat --proposer distinct    -> tout argument en plus va a "luikki serve",
rem                                        et un --proposer donne ici l'emporte
rem   set LUIKKI_PORT=8080 && luikki.bat
rem Ctrl+C, ou fermer la fenetre, arrete le serveur.

setlocal
cd /d "%~dp0"

if "%LUIKKI_PORT%"=="" set LUIKKI_PORT=8000
set PY=.venv\Scripts\luikki.exe

if not exist "%PY%" (
    echo .venv introuvable ou luikki non installe dans le venv.
    echo   python -m venv .venv ^&^& .venv\Scripts\pip install -e ".[web,dev]"
    pause
    exit /b 1
)

rem L'etape 5 part vers le GPU Modal (REMOTE_URL dans colour/remote.py) avec le
rem compte connecte dans l'appli (Compte).

rem Attend que le port reponde, puis ouvre le navigateur. En arriere-plan.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
 "1..120 | %%{ try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',%LUIKKI_PORT%); Start-Process 'http://127.0.0.1:%LUIKKI_PORT%/'; break } catch { Start-Sleep -Milliseconds 500 } }"

echo Luikki sur http://127.0.0.1:%LUIKKI_PORT%/  (Ctrl+C pour arreter)
rem --proposer remote avant %* : argparse garde la derniere valeur.
"%PY%" serve --port %LUIKKI_PORT% --proposer remote %*

endlocal
