import serial
import serial.tools.list_ports
import threading
import time
import sys
import os
import argparse
import queue
import codecs
import re
from datetime import datetime
import struct
import math

# ==================== 配置区域 ====================
# 在这里修改默认配置

# 串口默认配置
DEFAULT_PORT = None  # 默认端口，None表示自动选择
DEFAULT_BAUDRATE = 115200
DEFAULT_BYTESIZE = serial.EIGHTBITS
DEFAULT_PARITY = serial.PARITY_NONE
DEFAULT_STOPBITS = serial.STOPBITS_ONE
DEFAULT_TIMEOUT = 0.1
DEFAULT_WRITE_TIMEOUT = 0.1

# 显示配置
DEFAULT_SHOW_TIMESTAMP = False  # 是否显示时间戳
DEFAULT_HEX_DISPLAY = False     # 是否默认十六进制显示
DEFAULT_ENABLE_COLOR = True     # 是否启用颜色输出
DEFAULT_ENCODING = 'UTF-8'      # 默认编码格式

# 数据包处理配置
DEFAULT_PACKET_TIMEOUT = 0.01  # 数据包超时时间（秒）

# 连接配置
DEFAULT_CONNECTION_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0


# 支持的编码格式列表
SUPPORTED_ENCODINGS = [
    'UTF-8',
    'GB2312',
    'GBK',
    'ASCII',
    'Latin-1',
    'UTF-16',
    'UTF-16BE',
    'UTF-16LE',
    'ISO-8859-1'
]

# 功能配置
DEFAULT_LOG_ENABLED = False     # 是否启用数据记录
DEFAULT_MODBUS_PARSE_ENABLED = False  # 是否启用Modbus解析
DEFAULT_VISUALIZATION_ENABLED = False  # 是否启用数据可视化

# 数据记录配置
DEFAULT_LOG_FILENAME = None  # None表示自动生成

# 关键字筛选配置
DEFAULT_KEYWORD_FILTERS = {}  # 默认关键字筛选字典

# 可视化配置
DEFAULT_VISUALIZATION_MAX_POINTS = 1000

# ==================== 颜色配置 ====================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# 关键字颜色列表
KEYWORD_COLORS = [
    Colors.RED,      # 关键字1 - 红色
    Colors.GREEN,    # 关键字2 - 绿色
    Colors.YELLOW,   # 关键字3 - 黄色
    Colors.BLUE,     # 关键字4 - 蓝色
    Colors.MAGENTA,  # 关键字5 - 品红色
    Colors.CYAN,     # 关键字6 - 青色
    Colors.WHITE     # 关键字7 - 白色
]

# ==================== 常量定义 ====================
# 常用波特率列表
STANDARD_BAUDRATES = [
    300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 
    38400, 57600, 115200, 230400, 460800, 921600
]

# Modbus功能码
MODBUS_FUNCTIONS = {
    1: "Read Coils",
    2: "Read Discrete Inputs",
    3: "Read Holding Registers",
    4: "Read Input Registers",
    5: "Write Single Coil",
    6: "Write Single Register",
    15: "Write Multiple Coils",
    16: "Write Multiple Registers"
}

# ==================== 类定义 ====================
class DataVisualizer:
    """实时数据可视化类"""
    def __init__(self, max_points=DEFAULT_VISUALIZATION_MAX_POINTS):
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            from collections import deque
            self.plt = plt
            self.np = np
            self.deque = deque
        except ImportError:
            raise ImportError("matplotlib未安装，无法使用数据可视化功能")
        
        self.max_points = max_points
        self.data_buffer = self.deque(maxlen=max_points)
        self.time_buffer = self.deque(maxlen=max_points)
        self.fig, self.ax = self.plt.subplots(figsize=(10, 6))
        self.line, = self.ax.plot([], [], 'b-')
        self.ax.set_ylim(0, 255)
        self.ax.set_xlim(0, max_points)
        self.ax.grid(True)
        self.ax.set_title('实时串口数据')
        self.ax.set_xlabel('时间')
        self.ax.set_ylabel('数据值')
        self.start_time = time.time()
        self.is_running = False
        
    def update(self, data):
        """更新数据"""
        if not self.is_running:
            return
            
        current_time = time.time() - self.start_time
        if isinstance(data, (bytes, bytearray)):
            for byte in data:
                self.data_buffer.append(byte)
                self.time_buffer.append(current_time)
        else:
            self.data_buffer.append(data)
            self.time_buffer.append(current_time)
            
        # 更新图表
        if len(self.data_buffer) > 1:
            self.line.set_data(self.time_buffer, self.data_buffer)
            self.ax.set_xlim(max(0, current_time - 10), max(10, current_time))
            self.ax.set_ylim(min(0, min(self.data_buffer)), max(255, max(self.data_buffer)))
            self.plt.pause(0.01)
    
    def start(self):
        """启动可视化"""
        self.is_running = True
        self.plt.ion()
        self.plt.show()
        
    def stop(self):
        """停止可视化"""
        self.is_running = False
        self.plt.ioff()
        self.plt.close()

class SerialCommunicator:
    def __init__(self, port=DEFAULT_PORT, baudrate=DEFAULT_BAUDRATE, 
                 bytesize=DEFAULT_BYTESIZE, parity=DEFAULT_PARITY, 
                 stopbits=DEFAULT_STOPBITS, timeout=DEFAULT_TIMEOUT, 
                 write_timeout=DEFAULT_WRITE_TIMEOUT):
        # 串口配置
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.write_timeout = write_timeout
        
        # 状态变量
        self.ser = None
        self.running = False
        self.receive_thread = None
        self.data_queue = queue.Queue(maxsize=1000)
        self.hex_send = False
        self.hex_display = DEFAULT_HEX_DISPLAY
        self.receive_buffer = bytearray()
        self.current_encoding = DEFAULT_ENCODING
        self.decoder = self._create_decoder(self.current_encoding)
        self.last_print_time = time.time()
        self.packet_timeout = DEFAULT_PACKET_TIMEOUT
        self.show_timestamp = DEFAULT_SHOW_TIMESTAMP
        self.keyword_filters = DEFAULT_KEYWORD_FILTERS.copy()
        
        # 连接配置
        self.connection_retries = DEFAULT_CONNECTION_RETRIES
        self.retry_delay = DEFAULT_RETRY_DELAY
        
        # 统计信息
        self.receive_count = 0
        self.send_count = 0
        self.error_count = 0
        self.start_time = time.time()
        
        # 数据记录功能
        self.log_file = None
        self.log_enabled = DEFAULT_LOG_ENABLED
        
        # Modbus解析功能
        self.modbus_parse_enabled = DEFAULT_MODBUS_PARSE_ENABLED
        
        # 数据可视化
        self.visualizer = None
        self.visualization_enabled = DEFAULT_VISUALIZATION_ENABLED
        
        # 命令历史
        self.history_file = os.path.expanduser("~/.serial_tool_history")
        self._setup_history()
        
    def _create_decoder(self, encoding):
        """创建指定编码的解码器"""
        try:
            return codecs.getincrementaldecoder(encoding)("replace")
        except LookupError:
            print(f"{Colors.YELLOW}不支持的编码格式: {encoding}, 使用UTF-8代替{Colors.RESET}")
            return codecs.getincrementaldecoder("utf-8")("replace")
    
    def _setup_history(self):
        """设置命令历史"""
        try:
            import readline
            if os.path.exists(self.history_file):
                readline.read_history_file(self.history_file)
            readline.set_history_length(1000)
        except ImportError:
            pass
    
    def save_history(self):
        """保存命令历史"""
        try:
            import readline
            readline.write_history_file(self.history_file)
        except ImportError:
            pass
    
    def connect(self, retries=None, delay=None):
        """带重试机制的连接"""
        if retries is None:
            retries = self.connection_retries
        if delay is None:
            delay = self.retry_delay
            
        for attempt in range(retries):
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout
                )
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                print(f"{Colors.GREEN}已连接到串口 {self.port}，波特率 {self.baudrate}{Colors.RESET}")
                return True
            except serial.SerialException as e:
                if attempt < retries - 1:
                    print(f"{Colors.YELLOW}连接失败，{delay}秒后重试... ({attempt+1}/{retries}){Colors.RESET}")
                    time.sleep(delay)
                else:
                    print(f"{Colors.RED}连接串口失败: {e}{Colors.RESET}")
                    return False
    
    def start_receiving(self):
        """启动接收线程"""
        if not self.ser or not self.ser.is_open:
            print(f"{Colors.RED}串口未连接{Colors.RESET}")
            return False
            
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_data)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        # 启动数据处理线程
        self.process_thread = threading.Thread(target=self._process_data)
        self.process_thread.daemon = True
        self.process_thread.start()
        
        print(f"{Colors.GREEN}开始接收数据...{Colors.RESET}")
        return True
    
    def _receive_data(self):
        """接收数据的线程函数"""
        while self.running and self.ser and self.ser.is_open:
            try:
                # 使用内存视图提高性能
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    self.receive_count += len(data)
                    try:
                        self.data_queue.put(data, timeout=0.1)
                    except queue.Full:
                        # 队列已满，丢弃最旧的数据
                        try:
                            self.data_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self.data_queue.put(data, timeout=0.1)
                        
                    # 更新可视化
                    if self.visualization_enabled and self.visualizer:
                        self.visualizer.update(data)
            except serial.SerialException as e:
                if self.running:
                    print(f"{Colors.RED}串口通信错误: {e}{Colors.RESET}")
                    self.error_count += 1
                    # 尝试重新连接
                    if not self.connect():
                        break
            except Exception as e:
                if self.running:
                    print(f"{Colors.RED}接收数据错误: {e}{Colors.RESET}")
                    self.error_count += 1

    def _process_data(self):
        """处理数据的线程函数"""
        last_data_time = time.time()
        
        while self.running:
            try:
                # 获取数据
                try:
                    data = self.data_queue.get(timeout=0.05)
                    self.receive_buffer.extend(data)
                    last_data_time = time.time()
                except queue.Empty:
                    # 检查是否超时，需要处理缓冲区中的数据
                    if self.receive_buffer and time.time() - last_data_time > self.packet_timeout:
                        self._process_receive_buffer()
                        last_data_time = time.time()
                    continue
                
                # 检查是否收到完整的数据包（基于超时）
                if time.time() - last_data_time > self.packet_timeout:
                    self._process_receive_buffer()
                    last_data_time = time.time()
                    
            except Exception as e:
                if self.running:
                    print(f"{Colors.RED}处理数据错误: {e}{Colors.RESET}")
                    self.error_count += 1
                self.receive_buffer.clear()
    
    def _process_receive_buffer(self):
        """处理接收缓冲区中的数据"""
        if not self.receive_buffer:
            return
            
        # 记录原始数据
        raw_data = bytes(self.receive_buffer)
        
        # Modbus协议解析
        modbus_info = ""
        if self.modbus_parse_enabled:
            modbus_info = self._parse_modbus(raw_data)
            if modbus_info:
                print(f"{Colors.CYAN}{modbus_info}{Colors.RESET}")
        
        if self.hex_display:
            # 十六进制显示模式
            hex_str = ' '.join([f'{b:02X}' for b in self.receive_buffer])
            self._print_received_data(hex_str, is_hex=True, raw_data=raw_data)
        else:
            # 文本显示模式
            try:
                # 使用当前编码解码
                text = self.decoder.decode(bytes(self.receive_buffer), final=True)
                if text.strip():
                    self._print_received_data(text.strip(), raw_data=raw_data)
            except UnicodeDecodeError:
                # 解码失败，显示十六进制
                hex_str = ' '.join([f'{b:02X}' for b in self.receive_buffer])
                self._print_received_data(hex_str, is_hex=True, raw_data=raw_data)
        
        # 清空缓冲区
        self.receive_buffer.clear()
        self.decoder.reset()
    
    def _parse_modbus(self, data):
        """解析Modbus协议"""
        if len(data) < 8:  # Modbus RTU最小帧长度
            return ""
            
        try:
            # 提取从站地址
            slave_id = data[0]
            
            # 提取功能码
            function_code = data[1]
            function_name = MODBUS_FUNCTIONS.get(function_code, f"未知功能码 {function_code}")
            
            # 根据功能码解析
            if function_code in [1, 2, 3, 4]:
                # 读取请求
                start_addr = (data[2] << 8) + data[3]
                quantity = (data[4] << 8) + data[5]
                return f"Modbus请求: 从站 {slave_id}, {function_name}, 起始地址 {start_addr}, 数量 {quantity}"
                
            elif function_code in [5, 6]:
                # 写单个请求
                output_addr = (data[2] << 8) + data[3]
                output_value = (data[4] << 8) + data[5]
                return f"Modbus请求: 从站 {slave_id}, {function_name}, 地址 {output_addr}, 值 {output_value}"
                
            elif function_code in [15, 16]:
                # 写多个请求
                start_addr = (data[2] << 8) + data[3]
                quantity = (data[4] << 8) + data[5]
                byte_count = data[6]
                return f"Modbus请求: 从站 {slave_id}, {function_name}, 起始地址 {start_addr}, 数量 {quantity}, 字节数 {byte_count}"
                
            else:
                return f"Modbus: 从站 {slave_id}, {function_name}"
                
        except Exception as e:
            return f"Modbus解析错误: {e}"
    
    def _highlight_keywords(self, text):
        """使用正则表达式高效高亮关键字"""
        if not self.keyword_filters:
            return text
            
        # 构建正则表达式模式
        pattern = '|'.join(map(re.escape, self.keyword_filters.keys()))
        
        def replace_match(match):
            keyword = match.group(0)
            color_idx = self.keyword_filters.get(keyword, 0)
            color = KEYWORD_COLORS[color_idx % len(KEYWORD_COLORS)]
            return f"{color}{keyword}{Colors.BLUE}"
        
        # 使用正则表达式替换
        return re.sub(pattern, replace_match, text)
    
    def _print_received_data(self, data, is_hex=False, raw_data=None):
        """打印接收到的数据"""
        # 添加时间戳（如果启用）
        timestamp = ""
        if self.show_timestamp:
            timestamp = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
        
        # 处理关键字高亮
        if not is_hex and self.keyword_filters:
            highlighted_data = self._highlight_keywords(data)
            display_text = f"{Colors.BLUE}{timestamp}接收({self.current_encoding}): {highlighted_data}{Colors.RESET}"
        else:
            if is_hex:
                display_text = f"{Colors.MAGENTA}{timestamp}接收(十六进制): {data}{Colors.RESET}"
            else:
                display_text = f"{Colors.BLUE}{timestamp}接收({self.current_encoding}): {data}{Colors.RESET}"
        
        # 打印到控制台
        print(display_text)
        
        # 记录到文件（如果启用）
        if self.log_enabled and self.log_file:
            log_entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} - RECV({self.current_encoding}) - {data}\n"
            self.log_file.write(log_entry)
            self.log_file.flush()
    
    def send_data(self, data):
        """发送数据到串口"""
        if not self.ser or not self.ser.is_open:
            print(f"{Colors.RED}串口未连接{Colors.RESET}")
            return False
            
        try:
            # 保存原始输入用于显示
            original_input = data
            
            # 确保数据是字节格式
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            # 发送数据
            self.ser.write(data)
            self.send_count += len(data)
            
            # 直接显示用户输入的内容
            timestamp = ""
            if self.show_timestamp:
                timestamp = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
            
            display_text = f"{Colors.GREEN}{timestamp}发送: {original_input}{Colors.RESET}"
            print(display_text)
            
            # 记录到文件（如果启用）
            if self.log_enabled and self.log_file:
                log_entry = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} - SEND - {original_input}\n"
                self.log_file.write(log_entry)
                self.log_file.flush()
            
            return True
        except Exception as e:
            print(f"{Colors.RED}发送数据失败: {e}{Colors.RESET}")
            self.error_count += 1
            return False
    
    def set_encoding(self, encoding):
        """设置编码格式"""
        if encoding not in SUPPORTED_ENCODINGS:
            print(f"{Colors.RED}不支持的编码格式: {encoding}{Colors.RESET}")
            print(f"{Colors.YELLOW}支持的编码格式: {', '.join(SUPPORTED_ENCODINGS)}{Colors.RESET}")
            return False
            
        self.current_encoding = encoding
        self.decoder = self._create_decoder(encoding)
        print(f"{Colors.GREEN}编码格式已设置为: {encoding}{Colors.RESET}")
        return True
    
    def list_encodings(self):
        """列出所有支持的编码格式"""
        print(f"{Colors.CYAN}支持的编码格式:{Colors.RESET}")
        for i, encoding in enumerate(SUPPORTED_ENCODINGS, 1):
            marker = " *" if encoding == self.current_encoding else ""
            print(f"{Colors.CYAN}{i:2d}. {encoding}{marker}{Colors.RESET}")
    
    def enable_logging(self, filename=None):
        """启用数据记录"""
        if filename is None:
            # 获取当前脚本所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.join(script_dir, f"serial_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        else:
            # 如果用户提供了相对路径，也转换为基于脚本目录的绝对路径
            if not os.path.isabs(filename):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                filename = os.path.join(script_dir, filename)
        
        try:
            self.log_file = open(filename, 'a', encoding='utf-8')
            self.log_enabled = True
            # 获取文件的绝对路径并打印
            abs_path = os.path.abspath(filename)
            print(f"{Colors.GREEN}已启用数据记录到: {abs_path}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}启用数据记录失败: {e}{Colors.RESET}")
            return False

    def disable_logging(self):
        """禁用数据记录"""
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.log_enabled = False
        print(f"{Colors.YELLOW}已禁用数据记录{Colors.RESET}")
    
    def toggle_modbus_parse(self):
        """切换Modbus解析"""
        self.modbus_parse_enabled = not self.modbus_parse_enabled
        status = "开启" if self.modbus_parse_enabled else "关闭"
        print(f"{Colors.YELLOW}Modbus解析已{status}{Colors.RESET}")
    
    def toggle_visualization(self):
        """切换数据可视化"""
        try:
            import matplotlib
        except ImportError:
            print(f"{Colors.RED}数据可视化功能不可用，请安装matplotlib{Colors.RESET}")
            return
            
        if self.visualization_enabled:
            self.visualization_enabled = False
            if self.visualizer:
                self.visualizer.stop()
            print(f"{Colors.YELLOW}已关闭数据可视化{Colors.RESET}")
        else:
            try:
                self.visualizer = DataVisualizer()
                self.visualizer.start()
                self.visualization_enabled = True
                print(f"{Colors.GREEN}已开启数据可视化{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}启动数据可视化失败: {e}{Colors.RESET}")
    
    def show_statistics(self):
        """显示通信统计信息"""
        elapsed = time.time() - self.start_time
        print(f"{Colors.CYAN}=== 通信统计 ===")
        print(f"{Colors.CYAN}运行时间: {elapsed:.2f} 秒")
        print(f"{Colors.CYAN}接收字节: {self.receive_count}")
        print(f"{Colors.CYAN}发送字节: {self.send_count}")
        print(f"{Colors.CYAN}错误计数: {self.error_count}")
        print(f"{Colors.CYAN}当前编码: {self.current_encoding}")
        if elapsed > 0:
            print(f"{Colors.CYAN}接收速率: {self.receive_count/elapsed:.2f} 字节/秒")
            print(f"{Colors.CYAN}发送速率: {self.send_count/elapsed:.2f} 字节/秒")
        print(f"{Colors.CYAN}================{Colors.RESET}")
    
    def set_hex_send(self, hex_mode):
        """设置十六进制发送模式"""
        self.hex_send = hex_mode
        mode = "十六进制" if hex_mode else "文本"
        print(f"{Colors.YELLOW}发送模式已设置为: {mode}{Colors.RESET}")
    
    def set_hex_display(self, hex_mode):
        """设置十六进制显示模式"""
        self.hex_display = hex_mode
        mode = "十六进制" if hex_mode else "文本"
        print(f"{Colors.YELLOW}显示模式已设置为: {mode}{Colors.RESET}")
    
    def set_packet_timeout(self, timeout):
        """设置数据包超时时间"""
        self.packet_timeout = timeout
        print(f"{Colors.YELLOW}数据包超时时间已设置为: {timeout}秒{Colors.RESET}")
    
    def toggle_timestamp(self):
        """切换时间戳显示"""
        self.show_timestamp = not self.show_timestamp
        status = "开启" if self.show_timestamp else "关闭"
        print(f"{Colors.YELLOW}时间戳显示已{status}{Colors.RESET}")
    
    def add_filter_keyword(self, keyword):
        """添加筛选关键字"""
        if not keyword:
            return False
            
        if keyword in self.keyword_filters:
            print(f"{Colors.YELLOW}关键字 '{keyword}' 已存在{Colors.RESET}")
            return False
            
        # 分配颜色索引
        color_idx = len(self.keyword_filters) % len(KEYWORD_COLORS)
        self.keyword_filters[keyword] = color_idx
        
        color_name = ["红色", "绿色", "黄色", "蓝色", "品红色", "青色", "白色"][color_idx]
        print(f"{Colors.YELLOW}已添加筛选关键字: {keyword} ({color_name}){Colors.RESET}")
        return True
    
    def remove_filter_keyword(self, keyword):
        """移除筛选关键字"""
        if keyword in self.keyword_filters:
            del self.keyword_filters[keyword]
            print(f"{Colors.YELLOW}已移除筛选关键字: {keyword}{Colors.RESET}")
            return True
        else:
            print(f"{Colors.YELLOW}关键字 '{keyword}' 不存在{Colors.RESET}")
            return False
    
    def clear_filter_keywords(self):
        """清除所有筛选关键字"""
        self.keyword_filters.clear()
        print(f"{Colors.YELLOW}已清除所有筛选关键字{Colors.RESET}")
    
    def list_filter_keywords(self):
        """列出所有筛选关键字"""
        if not self.keyword_filters:
            print(f"{Colors.YELLOW}当前没有设置筛选关键字{Colors.RESET}")
            return
            
        print(f"{Colors.YELLOW}当前筛选关键字:{Colors.RESET}")
        for keyword, color_idx in self.keyword_filters.items():
            color_name = ["红色", "绿色", "黄色", "蓝色", "品红色", "青色", "白色"][color_idx]
            print(f"{Colors.YELLOW}  - {keyword} ({color_name}){Colors.RESET}")
    
    def change_baudrate(self, new_baudrate):
        """更改波特率"""
        if not self.ser or not self.ser.is_open:
            print(f"{Colors.RED}串口未连接{Colors.RESET}")
            return False
            
        try:
            self.ser.baudrate = new_baudrate
            self.baudrate = new_baudrate
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            print(f"{Colors.GREEN}波特率已更改为: {new_baudrate}{Colors.RESET}")
            return True
        except Exception as e:
            print(f"{Colors.RED}更改波特率失败: {e}{Colors.RESET}")
            return False
    
    def close(self):
        """关闭串口连接"""
        self.running = False
        if hasattr(self, 'receive_thread') and self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=0.5)
        if hasattr(self, 'process_thread') and self.process_thread and self.process_thread.is_alive():
            self.process_thread.join(timeout=0.5)
        if self.visualization_enabled and self.visualizer:
            self.visualizer.stop()
        if self.ser and self.ser.is_open:
            self.ser.close()
        if self.log_enabled and self.log_file:
            self.log_file.close()
        self.save_history()
        print(f"{Colors.YELLOW}串口已关闭{Colors.RESET}")

# ==================== 辅助函数 ====================
def list_serial_ports():
    """列出所有可用的串口设备"""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print(f"{Colors.RED}没有找到可用的串口设备{Colors.RESET}")
        return []
    
    print(f"{Colors.CYAN}可用的串口设备:{Colors.RESET}")
    for i, port in enumerate(ports):
        print(f"{Colors.CYAN}{i+1}. {port.device} - {port.description}{Colors.RESET}")
    return ports

def select_baudrate():
    """让用户选择波特率"""
    print(f"\n{Colors.CYAN}常用波特率列表:{Colors.RESET}")
    for i, baud in enumerate(STANDARD_BAUDRATES, 1):
        print(f"{Colors.CYAN}{i:2d}. {baud}{Colors.RESET}")
    
    while True:
        try:
            choice = input(f"\n{Colors.CYAN}请选择波特率编号 (1-{len(STANDARD_BAUDRATES)}), 或直接输入自定义波特率 (直接回车使用115200): {Colors.RESET}")
            
            # 如果用户直接按回车，使用默认波特率115200
            if choice == "":
                print(f"{Colors.YELLOW}使用默认波特率: {DEFAULT_BAUDRATE}{Colors.RESET}")
                return DEFAULT_BAUDRATE
                
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(STANDARD_BAUDRATES):
                    return STANDARD_BAUDRATES[choice_num - 1]
                else:
                    # 如果数字不在列表范围内，尝试作为自定义波特率
                    return int(choice)
            else:
                # 如果不是数字，尝试作为自定义波特率
                try:
                    return int(choice)
                except ValueError:
                    print(f"{Colors.RED}无效的输入，请输入数字或波特率值{Colors.RESET}")
        except ValueError:
            print(f"{Colors.RED}无效的波特率值{Colors.RESET}")

def setup_autocomplete():
    """设置命令自动补全"""
    try:
        import readline
        import rlcompleter
        
        # 定义可用的命令
        commands = [
            'send', 'hex', 'timeout', 'baud', 'timestamp', 
            'filter add', 'filter remove', 'filter clear', 'filter list',
            'quit', 'exit', 'stats', 'log', 'nolog', 'modbus',
            'visual', 'help', 'encoding', 'encodings'
        ]
        
        # 设置补全函数
        def complete(text, state):
            options = [cmd for cmd in commands if cmd.startswith(text)]
            if state < len(options):
                return options[state]
            else:
                return None
        
        readline.set_completer(complete)
        readline.parse_and_bind("tab: complete")
    except ImportError:
        pass

# ==================== 主函数 ====================
def main():
    parser = argparse.ArgumentParser(description='增强版串口通信工具')
    parser.add_argument('-p', '--port', default=DEFAULT_PORT, 
                       help=f'串口设备名称 (如: COM3, /dev/ttyUSB0) (默认: {DEFAULT_PORT})')
    parser.add_argument('-b', '--baudrate', type=int, default=DEFAULT_BAUDRATE, 
                       help=f'波特率 (默认: {DEFAULT_BAUDRATE})')
    parser.add_argument('-e', '--encoding', default=DEFAULT_ENCODING,
                       help=f'编码格式 (默认: {DEFAULT_ENCODING})')
    parser.add_argument('-l', '--list', action='store_true', 
                       help='列出所有可用的串口设备')
    parser.add_argument('-c', '--color', action='store_true', default=DEFAULT_ENABLE_COLOR,
                       help=f'启用彩色输出 (默认: {"启用" if DEFAULT_ENABLE_COLOR else "禁用"})')
    parser.add_argument('-nc', '--no-color', action='store_false', dest='color',
                       help='禁用彩色输出')
    parser.add_argument('-t', '--timeout', type=float, default=DEFAULT_PACKET_TIMEOUT,
                       help=f'数据包超时时间 (默认: {DEFAULT_PACKET_TIMEOUT}秒)')
    parser.add_argument('-ts', '--timestamp', action='store_true', default=DEFAULT_SHOW_TIMESTAMP,
                       help=f'启用时间戳显示 (默认: {"启用" if DEFAULT_SHOW_TIMESTAMP else "关闭"})')
    parser.add_argument('-log', '--log', action='store_true', default=DEFAULT_LOG_ENABLED,
                       help=f'启用数据记录 (默认: {"启用" if DEFAULT_LOG_ENABLED else "关闭"})')
    parser.add_argument('-retry', '--retry', type=int, default=DEFAULT_CONNECTION_RETRIES,
                       help=f'连接重试次数 (默认: {DEFAULT_CONNECTION_RETRIES})')
    parser.add_argument('-delay', '--delay', type=float, default=DEFAULT_RETRY_DELAY,
                       help=f'连接重试延迟 (默认: {DEFAULT_RETRY_DELAY}秒)')
    parser.add_argument('-modbus', '--modbus', action='store_true', default=DEFAULT_MODBUS_PARSE_ENABLED,
                       help=f'启用Modbus解析 (默认: {"启用" if DEFAULT_MODBUS_PARSE_ENABLED else "关闭"})')
    parser.add_argument('-visual', '--visual', action='store_true', default=DEFAULT_VISUALIZATION_ENABLED,
                       help=f'启用数据可视化 (默认: {"启用" if DEFAULT_VISUALIZATION_ENABLED else "关闭"})')
    
    args = parser.parse_args()
    
    # 如果禁用颜色，将所有颜色代码设为空字符串
    if not args.color:
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')
    
    if args.list:
        list_serial_ports()
        return
    
    # 检查编码格式是否支持
    if args.encoding not in SUPPORTED_ENCODINGS:
        print(f"{Colors.YELLOW}不支持的编码格式: {args.encoding}, 使用默认编码: {DEFAULT_ENCODING}{Colors.RESET}")
        args.encoding = DEFAULT_ENCODING
    
    # 设置命令自动补全
    setup_autocomplete()
    
    # 确定波特率
    baudrate = args.baudrate
    
    port_name = args.port
    if not port_name:
        ports = list_serial_ports()
        if not ports:
            return
        
        try:
            choice = int(input(f"{Colors.CYAN}请选择要使用的串口设备编号: {Colors.RESET}")) - 1
            if 0 <= choice < len(ports):
                port_name = ports[choice].device
            else:
                print(f"{Colors.RED}无效的选择{Colors.RESET}")
                return
        except ValueError:
            print(f"{Colors.RED}请输入有效的数字{Colors.RESET}")
            return
        
        # 如果没有通过命令行指定波特率，让用户选择
        if args.baudrate == DEFAULT_BAUDRATE:
            baudrate = select_baudrate()
    
    # 创建串口通信对象
    communicator = SerialCommunicator(port=port_name, baudrate=baudrate)
    communicator.set_packet_timeout(args.timeout)
    communicator.connection_retries = args.retry
    communicator.retry_delay = args.delay
    communicator.show_timestamp = args.timestamp
    communicator.modbus_parse_enabled = args.modbus
    communicator.visualization_enabled = args.visual
    
    # 设置编码格式
    communicator.set_encoding(args.encoding)
    
    # 设置数据记录
    if args.log:
        communicator.enable_logging()
    
    # 连接串口
    if not communicator.connect():
        return
    
    # 启动接收线程
    if not communicator.start_receiving():
        communicator.close()
        return
    
    print(f"\n{Colors.GREEN}增强版串口通信工具已启动{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 直接发送消息，例如: send Hello World{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'hex' 切换十六进制显示模式{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'timeout <秒数>' 设置数据包超时时间，例如: timeout 0.05{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'baud <波特率>' 更改波特率，例如: baud 9600{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'timestamp' 切换时间戳显示{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'encoding <编码>' 设置编码格式，例如: encoding GB2312{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'encodings' 列出所有支持的编码格式{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter add <关键字>' 添加筛选关键字，例如: filter add ERROR{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter remove <关键字>' 移除筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter clear' 清除所有筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter list' 列出所有筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'log' 启用数据记录{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'nolog' 禁用数据记录{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'modbus' 切换Modbus协议解析{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'visual' 切换数据可视化{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'stats' 显示通信统计{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'help' 显示帮助信息{Colors.RESET}")
    print(f"{Colors.CYAN}{'-' * 50}{Colors.RESET}")
    
    try:
        while True:
            user_input = input()
            
            if user_input.lower() in ['quit', 'exit']:
                break
            elif user_input.lower().startswith('send '):
                # 发送指定消息
                message = user_input[5:]
                communicator.send_data(message + '\n')
            elif user_input.lower() == 'hex':
                # 切换十六进制显示模式
                communicator.set_hex_display(not communicator.hex_display)
            elif user_input.lower().startswith('timeout '):
                # 设置超时时间
                try:
                    timeout = float(user_input[8:])
                    communicator.set_packet_timeout(timeout)
                except ValueError:
                    print(f"{Colors.RED}无效的超时时间值{Colors.RESET}")
            elif user_input.lower().startswith('baud '):
                # 更改波特率
                try:
                    new_baudrate = int(user_input[5:])
                    communicator.change_baudrate(new_baudrate)
                except ValueError:
                    print(f"{Colors.RED}无效的波特率值{Colors.RESET}")
            elif user_input.lower() == 'timestamp':
                # 切换时间戳显示
                communicator.toggle_timestamp()
            elif user_input.lower().startswith('encoding '):
                # 设置编码格式
                encoding = user_input[9:]
                communicator.set_encoding(encoding)
            elif user_input.lower() == 'encodings':
                # 列出所有支持的编码格式
                communicator.list_encodings()
            elif user_input.lower().startswith('filter add '):
                # 添加筛选关键字
                keyword = user_input[11:]
                communicator.add_filter_keyword(keyword)
            elif user_input.lower().startswith('filter remove '):
                # 移除筛选关键字
                keyword = user_input[14:]
                communicator.remove_filter_keyword(keyword)
            elif user_input.lower() == 'filter clear':
                # 清除所有筛选关键字
                communicator.clear_filter_keywords()
            elif user_input.lower() == 'filter list':
                # 列出所有筛选关键字
                communicator.list_filter_keywords()
            elif user_input.lower() == 'log':
                # 启用数据记录
                communicator.enable_logging()
            elif user_input.lower() == 'nolog':
                # 禁用数据记录
                communicator.disable_logging()
            elif user_input.lower() == 'modbus':
                # 切换Modbus解析
                communicator.toggle_modbus_parse()
            elif user_input.lower() == 'visual':
                # 切换数据可视化
                communicator.toggle_visualization()
            elif user_input.lower() == 'stats':
                # 显示统计信息
                communicator.show_statistics()
            elif user_input.lower() == 'help':
                # 显示帮助信息
                print(f"{Colors.CYAN}=== 帮助信息 ===")
                print(f"{Colors.CYAN}请参考程序启动时的命令列表{Colors.RESET}")
                print(f"{Colors.CYAN}================{Colors.RESET}")
            elif user_input:
                # 直接发送输入的消息
                communicator.send_data(user_input + '\n')
                
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}程序被用户中断{Colors.RESET}")
    finally:
        communicator.close()

if __name__ == "__main__":
    # 检查是否安装了pyserial
    try:
        import serial
    except ImportError:
        print(f"{Colors.RED}错误: 未找到pyserial库{Colors.RESET}")
        print(f"{Colors.RED}请先安装pyserial: pip install pyserial{Colors.RESET}")
        sys.exit(1)
    
    main()