# build_serial_tool.py
import PyInstaller.__main__
import os
import sys
import shutil

current_dir = os.path.dirname(os.path.abspath(__file__))
main_script = os.path.join(current_dir, 'serial_tool.py') # 主脚本文件

if not os.path.exists(main_script):
    print(f"错误: 找不到主脚本文件 '{main_script}'")
    print("请确保文件存在于同一目录下")
    input("按回车键退出...")
    sys.exit(1)

params = [
    main_script,
    '--name=SerialTool',        # 生成可执行文件名称
    '--onefile',                # 生成单文件
    '--console',                # 控制台程序
    '--clean',                  # 清理以前的构建文件
    '--distpath=./dist',        # 生成文件路径
    '--workpath=./build',       # 工作路径
    '--specpath=./',            # spec文件路径
    '--hidden-import=serial.serialposix',       # 解决部分系统缺少serial模块的问题
    '--hidden-import=serial.serialwin32',       # 解决部分系统缺少serial模块的问题
    '--hidden-import=matplotlib.backends.backend_tkagg',# 解决部分系统缺少tkagg模块的问题
    '--hidden-import=matplotlib.pyplot',        # 解决部分系统缺少pyplot模块的问题
    '--hidden-import=numpy',                    # 解决部分系统缺少numpy模块的问题
    '--hidden-import=queue',                    # 解决部分系统缺少queue模块的问题
    '--hidden-import=codecs',                   # 解决部分系统缺少codecs模块的问题
    '--hidden-import=re',                       # 解决部分系统缺少re模块的问题
    '--hidden-import=struct',                   # 解决部分系统缺少struct模块的问题
    '--hidden-import=math',                     # 解决部分系统缺少math模块的问题
    '--hidden-import=datetime',                 # 解决部分系统缺少datetime模块的问题
]

if sys.platform.startswith('win'):
    params.append('--hidden-import=pyreadline')
else:
    params.append('--hidden-import=readline')

print("正在打包，请稍候...")
PyInstaller.__main__.run(params)

# 删除 build、spec，只保留 dist
try:
    if os.path.exists("build"):
        shutil.rmtree("build")
    spec_file = os.path.join(current_dir, "SerialTool.spec")
    if os.path.exists(spec_file):
        os.remove(spec_file)
    print("清理完成，仅保留 dist 文件夹。")
except Exception as e:
    print(f"清理过程出错: {e}")

input("打包完成！按回车键退出...")
