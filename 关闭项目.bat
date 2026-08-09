@echo off
REM Stop the douyin-auto-fire management panel (no visible window).
REM PowerShell resolves every panel.py process AND the port-8765 owner, then
REM taskkill /T tears down each whole process tree (parent + forked child that
REM holds the socket). No wmic, no Get-NetTCPConnection (both flaky here).
set PORT=8765
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$ids=@(); $ids+=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and ($_.CommandLine -like '*panel.py*') } | ForEach-Object { $_.ProcessId }); $raw=netstat -ano 2>$null; foreach ($l in $raw) { if ($l -match ':%PORT%\s' -and $l -match 'LISTEN') { $ids+=($l -split '\s+')[-1] } }; $ids=@($ids | Where-Object { $_ } | Sort-Object -Unique); foreach ($id in $ids) { & taskkill.exe /PID $id /F /T 2>$null }" >nul 2>&1
goto :eof
