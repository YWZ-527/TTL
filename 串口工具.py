import serial
import serial.tools.list_ports
import threading
import time
import sys
import argparse
import queue
import codecs
from datetime import datetime

# 颜色代码
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

# 关键字颜色列表 - 不同的关键字使用不同的颜色
KEYWORD_COLORS = [
    Colors.RED,      # 关键字1 - 红色
    Colors.GREEN,    # 关键字2 - 绿色
    Colors.YELLOW,   # 关键字3 - 黄色
    Colors.BLUE,     # 关键字4 - 蓝色
    Colors.MAGENTA,  # 关键字5 - 品红色
    Colors.CYAN,     # 关键字6 - 青色
    Colors.WHITE     # 关键字7 - 白色
]

# 常用波特率列表
STANDARD_BAUDRATES = [
    300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 28800, 
    38400, 57600, 115200, 230400, 460800, 921600
]

class SerialCommunicator:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = False
        self.receive_thread = None
        self.data_queue = queue.Queue(maxsize=1000)
        self.hex_send = False
        self.hex_display = False
        self.receive_buffer = bytearray()
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.last_print_time = time.time()
        self.packet_timeout = 0.01  # 默认数据包超时时间改为0.01秒
        self.show_timestamp = False  # 时间戳显示开关，默认关闭
        self.keyword_filters = {}    # 关键字筛选字典，key: 关键字, value: 颜色索引
        
    def connect(self):
        """连接串口"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=0.1
            )
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            print(f"{Colors.GREEN}已连接到串口 {self.port}，波特率 {self.baudrate}{Colors.RESET}")
            return True
        except serial.SerialException as e:
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
                # 读取数据
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    try:
                        self.data_queue.put(data, timeout=0.1)
                    except queue.Full:
                        # 队列已满，丢弃最旧的数据
                        try:
                            self.data_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self.data_queue.put(data, timeout=0.1)
            except Exception as e:
                if self.running:
                    print(f"{Colors.RED}接收数据错误: {e}{Colors.RESET}")
                break

    def _process_data(self):
        """处理数据的线程函数 - 优化数据包重组"""
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
                self.receive_buffer.clear()
    
    def _process_receive_buffer(self):
        """处理接收缓冲区中的数据"""
        if not self.receive_buffer:
            return
            
        if self.hex_display:
            # 十六进制显示模式
            hex_str = ' '.join([f'{b:02X}' for b in self.receive_buffer])
            self._print_received_data(hex_str, is_hex=True)
        else:
            # 文本显示模式
            try:
                # 尝试解码为UTF-8
                text = self.decoder.decode(bytes(self.receive_buffer), final=True)
                if text.strip():
                    self._print_received_data(text.strip())
            except UnicodeDecodeError:
                # 解码失败，显示十六进制
                hex_str = ' '.join([f'{b:02X}' for b in self.receive_buffer])
                self._print_received_data(hex_str, is_hex=True)
        
        # 清空缓冲区
        self.receive_buffer.clear()
        self.decoder.reset()  # 重置解码器
    
    def _print_received_data(self, data, is_hex=False):
        """打印接收到的数据，支持时间戳和关键字筛选"""
        # 添加时间戳（如果启用）
        timestamp = ""
        if self.show_timestamp:
            timestamp = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
        
        # 检查关键字筛选
        matched_keyword = None
        matched_color = None
        
        for keyword, color_idx in self.keyword_filters.items():
            if keyword in data:
                matched_keyword = keyword
                matched_color = KEYWORD_COLORS[color_idx % len(KEYWORD_COLORS)]
                break
        
        # 根据匹配情况选择颜色
        if matched_keyword:
            # 使用匹配关键字的颜色
            if is_hex:
                print(f"{matched_color}{timestamp}接收(十六进制): {data}{Colors.RESET}")
            else:
                print(f"{matched_color}{timestamp}接收: {data}{Colors.RESET}")
        else:
            # 正常显示
            if is_hex:
                print(f"{Colors.MAGENTA}{timestamp}接收(十六进制): {data}{Colors.RESET}")
            else:
                print(f"{Colors.BLUE}{timestamp}接收: {data}{Colors.RESET}")
    
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
            
            # 直接显示用户输入的内容
            timestamp = ""
            if self.show_timestamp:
                timestamp = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
            print(f"{Colors.GREEN}{timestamp}发送: {original_input}{Colors.RESET}")
            
            return True
        except Exception as e:
            print(f"{Colors.RED}发送数据失败: {e}{Colors.RESET}")
            return False
    
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
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"{Colors.YELLOW}串口已关闭{Colors.RESET}")

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
                print(f"{Colors.YELLOW}使用默认波特率: 115200{Colors.RESET}")
                return 115200
                
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

def main():
    parser = argparse.ArgumentParser(description='高速串口通信工具 - 支持发送和接收数据')
    parser.add_argument('-p', '--port', help='串口设备名称 (如: COM3, /dev/ttyUSB0)')
    parser.add_argument('-b', '--baudrate', type=int, default=None, 
                       help='波特率 (默认: 115200)')
    parser.add_argument('-l', '--list', action='store_true', 
                       help='列出所有可用的串口设备')
    parser.add_argument('-c', '--color', action='store_true', default=True,
                       help='启用彩色输出 (默认: 启用)')
    parser.add_argument('-nc', '--no-color', action='store_false', dest='color',
                       help='禁用彩色输出')
    parser.add_argument('-t', '--timeout', type=float, default=0.01,
                       help='数据包超时时间 (默认: 0.01秒)')
    parser.add_argument('-ts', '--timestamp', action='store_true', default=False,
                       help='启用时间戳显示 (默认: 关闭)')
    
    args = parser.parse_args()
    
    # 如果禁用颜色，将所有颜色代码设为空字符串
    if not args.color:
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')
    
    if args.list:
        list_serial_ports()
        return
    
    # 确定波特率
    baudrate = args.baudrate if args.baudrate is not None else 115200
    
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
        if args.baudrate is None:
            baudrate = select_baudrate()
    
    # 创建串口通信对象
    communicator = SerialCommunicator(port_name, baudrate)
    communicator.set_packet_timeout(args.timeout)
    
    # 设置时间戳显示
    if args.timestamp:
        communicator.toggle_timestamp()
    
    # 连接串口
    if not communicator.connect():
        return
    
    # 启动接收线程
    if not communicator.start_receiving():
        communicator.close()
        return
    
    print(f"\n{Colors.GREEN}高速串口通信工具已启动{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'quit' 或 'exit' 退出程序{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'send <消息>' 发送消息，例如: send Hello World{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'hex' 切换十六进制显示模式{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'timeout <秒数>' 设置数据包超时时间，例如: timeout 0.05{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'baud <波特率>' 更改波特率，例如: baud 9600{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'timestamp' 切换时间戳显示{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter add <关键字>' 添加筛选关键字，例如: filter add ERROR{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter remove <关键字>' 移除筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter clear' 清除所有筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}输入 'filter list' 列出所有筛选关键字{Colors.RESET}")
    print(f"{Colors.YELLOW}直接输入消息并按回车键发送{Colors.RESET}")
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