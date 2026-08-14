@echo off
chcp 65001 >nul
title AI Interview Agent - xiaozhi Bridge
cd /d "%~dp0"

echo ========================================
echo   AI Interview Agent - xiaozhi Bridge
echo ========================================
echo WebSocket 默认地址: ws://0.0.0.0:8089/xiaozhi/v1/
echo 手机请填写电脑的局域网 IP，例如 ws://192.168.1.100:8089/xiaozhi/v1/
echo.
echo 首次运行请执行：
echo   python -m pip install -r deploy/requirements_full.txt
echo   copy .env.example .env
echo.
echo 按 Ctrl+C 停止服务。
echo ========================================

python services\xiaozhi_bridge.py
pause
