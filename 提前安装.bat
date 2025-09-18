@echo off
echo 正在安装串口通信工具所需依赖...
echo.

echo 1. 检查Python安装...
python --version
if errorlevel 1 (
    echo Python未安装，请先安装Python并确保勾选"Add Python to PATH"
    echo 访问 https://www.python.org/downloads/ 下载安装
    pause
    exit /b 1
)

echo.
echo 2. 安装必需库...
pip install pyserial

echo.
echo 3. 安装可选库（数据可视化）...
pip install matplotlib

echo.
echo 4. 安装可选库（命令自动补全）...
pip install pyreadline3

echo.
echo 安装完成！
echo 现在可以运行: python serial_tool.py
pause