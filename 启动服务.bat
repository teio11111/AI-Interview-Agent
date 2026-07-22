@echo off
chcp 65001 >nul
title AI Interview Agent
cd /d "%~dp0"
echo 正在启动 AI 面试系统...
echo 启动后访问: http://127.0.0.1:8088
echo 关闭此窗口即可停止服务
echo ========================================
python app.py
pause
