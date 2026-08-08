@echo off
rem RAG Forge Agentic Chat 一键启动（双击运行）
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=src
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_DISABLE_TLS_VERIFY=1
echo.
echo 启动 RAG Forge Agentic Chat ...
echo.
python scripts\chat.py
echo.
pause
