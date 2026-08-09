@echo off
REM Start the douyin-auto-fire management panel in the background (no visible window),
REM auto-clearing any old instance first, then open the browser.
cd /d "%~dp0"
set PORT=8765
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$ids=@(); $ids+=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and ($_.CommandLine -like '*panel.py*') } | ForEach-Object { $_.ProcessId }); $raw=netstat -ano 2>$null; foreach ($l in $raw) { if ($l -match ':%PORT%\s' -and $l -match 'LISTEN') { $ids+=($l -split '\s+')[-1] } }; $ids=@($ids | Where-Object { $_ } | Sort-Object -Unique); foreach ($id in $ids) { & taskkill.exe /PID $id /F /T 2>$null }" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList '%~dp0panel.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
for /L %%n in (1,1,15) do (
    powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "try { if ((Invoke-WebRequest -Uri http://127.0.0.1:8765 -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode -eq 200) { exit 0 } } catch {} exit 1" >nul 2>&1
    if not errorlevel 1 goto :ready
    timeout /t 1 >nul
)
:ready
start "" http://127.0.0.1:8765
goto :eof
