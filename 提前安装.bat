@echo off
echo ���ڰ�װ����ͨ�Ź�����������...
echo.

echo 1. ���Python��װ...
python --version
if errorlevel 1 (
    echo Pythonδ��װ�����Ȱ�װPython��ȷ����ѡ"Add Python to PATH"
    echo ���� https://www.python.org/downloads/ ���ذ�װ
    pause
    exit /b 1
)

echo.
echo 2. ��װ�����...
pip install pyserial

echo.
echo 3. ��װ��ѡ�⣨���ݿ��ӻ���...
pip install matplotlib

echo.
echo 4. ��װ��ѡ�⣨�����Զ���ȫ��...
pip install pyreadline3

echo.
echo ��װ��ɣ�
echo ���ڿ�������: python serial_tool.py
pause