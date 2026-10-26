@echo off
REM 妙搭小站 · 本机后端一键启动
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [首次运行] 创建虚拟环境并安装依赖...
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
echo [启动] http://127.0.0.1:5000
.venv\Scripts\python app.py
