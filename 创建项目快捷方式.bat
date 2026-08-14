@echo off
chcp 65001 > nul
REM ============================================================
REM  xiaozhi-unity 项目快捷方式创建脚本
REM ============================================================
REM  在桌面创建两个快捷方式：
REM    1. Unity Editor (国际版 2022.3.62f3c1)
REM    2. xiaozhi-unity 项目 (双击直接打开项目)
REM ============================================================

set EDITOR_EXE=C:\Program Files\Unity\Hub\Editor\2022.3.62f3c1\Editor\Unity.exe
set PROJECT_DIR=C:\Users\Teio\Desktop\XiaozhiInterview\Project
set DESKTOP=%USERPROFILE%\Desktop

echo ============================================
echo   Creating desktop shortcuts
echo ============================================
echo.

REM 验证 Editor 存在
if not exist "%EDITOR_EXE%" (
    echo [ERROR] Unity Editor not found: %EDITOR_EXE%
    pause
    exit /b 1
)

REM 验证项目存在
if not exist "%PROJECT_DIR%\ProjectSettings\ProjectVersion.txt" (
    echo [ERROR] Project not found: %PROJECT_DIR%
    pause
    exit /b 1
)

echo [OK] Unity Editor: %EDITOR_EXE%
echo [OK] Project: %PROJECT_DIR%
echo.

REM 用 PowerShell 建快捷方式 (更可靠)
powershell -NoProfile -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell" ^
  "$Shortcut = $WshShell.CreateShortcut('%DESKTOP%\xiaozhi-unity.lnk')" ^
  "$Shortcut.TargetPath = '%EDITOR_EXE%'" ^
  "$Shortcut.Arguments = '-projectPath \"%PROJECT_DIR%\"'" ^
  "$Shortcut.WorkingDirectory = '%PROJECT_DIR%'" ^
  "$Shortcut.IconLocation = '%EDITOR_EXE%,0'" ^
  "$Shortcut.Description = 'xiaozhi-unity (Unity 2022.3.62f3c1)'" ^
  "$Shortcut.Save()" ^
  "Write-Host '  [OK] Created: xiaozhi-unity.lnk on Desktop' -ForegroundColor Green"

echo.

powershell -NoProfile -Command ^
  "$WshShell = New-Object -ComObject WScript.Shell" ^
  "$Shortcut = $WshShell.CreateShortcut('%DESKTOP%\Unity 2022.3.62f3c1.lnk')" ^
  "$Shortcut.TargetPath = '%EDITOR_EXE%'" ^
  "$Shortcut.IconLocation = '%EDITOR_EXE%,0'" ^
  "$Shortcut.Description = 'Unity Editor 2022.3.62f3c1 (without Hub)'" ^
  "$Shortcut.Save()" ^
  "Write-Host '  [OK] Created: Unity 2022.3.62f3c1.lnk on Desktop' -ForegroundColor Green"

echo.
echo ============================================
echo   Done! Check your desktop.
echo ============================================
echo.
echo   xiaozhi-unity.lnk         - 双击直接打开项目
echo   Unity 2022.3.62f3c1.lnk  - 启动 Unity Editor (空项目界面)
echo.
pause