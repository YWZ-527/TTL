# build_serial_tool.py
import PyInstaller.__main__
import os

# 获取当前目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 定义打包参数
params = [
    'serial_tool.py',           # 主脚本文件
    '--name=SerialTool',        # 可执行文件名称
    '--onefile',                # 打包成单个文件
    '--console',                # 控制台应用程序
    '--icon=NONE',              # 无图标
    '--add-data=README.md;.',   # 添加README文件（如果有）
    '--hidden-import=serial.serialposix',  # 隐藏导入
    '--hidden-import=serial.serialwin32',  # 隐藏导入
    '--clean',                  # 清理临时文件
]

# 执行打包
PyInstaller.__main__.run(params)