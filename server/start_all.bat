@echo off
REM 妙搭小站 · 本机后端一键启动（MySQL + Flask）
REM 首次使用前请先运行 setup.bat 完成 MySQL 初始化与依赖安装
cd /d "%~dp0"

REM ---- 1. MySQL ----
netstat -an | findstr ":3306" | findstr "LISTENING" >nul
if %errorlevel%==0 (
  echo [MySQL] 已在运行
) else (
  echo [MySQL] 启动中...
  start "miaoda-mysql" /min "D:\mysql-8.0.45\mysql-8.0.45-winx64\bin\mysqld.exe" --datadir=D:\mysql-data
  timeout /t 5 /nobreak >nul
)

REM ---- 2. Flask 后端 ----
netstat -an | findstr ":5000" | findstr "LISTENING" >nul
if %errorlevel%==0 (
  echo [后端] 已在运行  http://127.0.0.1:5000
) else (
  if not exist ".venv\Scripts\python.exe" (
    echo [首次] 创建虚拟环境并安装依赖...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
  )
  echo [后端] 启动中  http://127.0.0.1:5000
  start "miaoda-server" /min cmd /c ".venv\Scripts\python app.py"
)

echo 完成。账号与排行榜页：打开网站后进入「账号与排行榜」。
