import requests
import string
import time
import threading
import random
import os
import signal
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

cookies = {
    '_octo': 'GH1.1.667271224.1727398439',
    '_device_id': 'd9138661889f09e7d9dfc5b8f20afeb8',
    'GHCC': 'Required:1-Analytics:1-SocialMedia:1-Advertising:1',
    'MicrosoftApplicationsTelemetryDeviceId': 'a6c4f4e6-fb6b-47cd-8b84-67400b7352e4',
    'MSFPC': 'GUID=e854b30ec1564e38b24be8f9ed269900&HASH=e854&LV=202409&V=4&LU=1727341919785',
    'color_mode': '%7B%22color_mode%22%3A%22auto%22%2C%22light_theme%22%3A%7B%22name%22%3A%22light%22%2C%22color_mode%22%3A%22light%22%7D%2C%22dark_theme%22%3A%7B%22name%22%3A%22dark%22%2C%22color_mode%22%3A%22dark%22%7D%7D',
    'cpu_bucket': 'xlg',
    'preferred_color_mode': 'light',
    'tz': 'Asia%2FShanghai',
    'saved_user_sessions': '186833005%3ApIDVkz2WL3_bW3jtvoyGCIQF6eHgIQegT9wDWQlgHC_GBB_5%7C190329462%3ALkbCi3lTbqn8sgeJ0XbB9IM-WFRTpQW4VB34l9az_xa0SIfJ%7C87361183%3AGnhmBuwPxnv6oiIp3qL5W-pAG7lby8KcEGaywBemXmwdPjrZ',
    'logged_in': 'no',
    '_gh_sess': '3piV%2BKEt%2FLzyFv6tTSCNOYlDU%2B9WMSX3NuSdLDJBujNDPjnl%2Fyh023BDQCgYT5C%2B%2BNc1hn%2BiPyu4rySXcx6AQzzU1u05J1XKCxVwni004iZtjX%2BNobPB0Q5d1Id7S%2B%2FtIq7DP2ExBVSL2dpyCS3%2FN1ezis5NMv6l9oq4kGsEl62NiEA1uOKB26SQ6UpQasErcufEID%2BKxTvSsxwM0oRDRlDGpbwLlhLPnPz%2BkclPZurbLvifNSSIlcQaek4l8mFt0Bs4AWtRFFKKYq5mdYtL%2FFDJ6l5lLwn3kuqFltsEFFQTRidysEXBwlbusCXVJo1AdW7Qn7PmfEjlt%2FI5iZTJMXScNzGnuJnXV%2BO5Wz5X8kC8vpv0mnt658Bd12acwgSkySOhwiHbUzSX5%2BeQCw%2FlFDGiNwOU7b80prOK5EeHkehPRM8fDlMTH8KaE5XONyJTb9EzZHFkZ87M6nGsfq7Zo%2BVi6taVjICQihbuBLv%2BszcT6o0Gz6xEYb1Du7LYz02asTK%2BUOHB13Ru%2BgzLLQmTkLTMvM3HdTtfhOMYRv%2BtBZNH0ST1Y9eyox0CFQ5eTi%2BN5lqHQmpBic3WFoEg3%2BxzYaEN2xNezbt3XKjEkG6CmCRrkFdTRxX%2Fa%2BIcdpgXbFyCMoNqV25TXI0hxTOJD1kw5PPmJyzkupSh0VN8l89otp0rdYQ%2Btg5syPRz48Q8wb8qaIZDqc98wdsmcId%2F4Kx9Y5ZD%2BcpwoB%2BYJumWAZVMb9%2BDSS7PcJg3dRf5SpAfewgpQcYHykhpawaMr%2FaGIi8y4zbAUP%2FMs1KifIBUrT1dBVOvfT4oQ9vtemoxpsEtuxyA22I0d49nddkzIBqX--eQhEa8UNvvOZLvhZ--BCyoIuKqWnqAqUdIp83BNw%3D%3D',
}

headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://github.com/signup?return_to=%2F&source=login',
    'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
}

# 线程安全的文件写入锁
file_lock = threading.Lock()
# 进度条更新锁
progress_lock = threading.Lock()

# 添加全局变量用于追踪运行状态和进度保存
running = True
last_saved_progress = 0
progress_save_interval = 60  # 每60秒保存一次进度

# 修改速率限制器使用更小的时间窗口
class RateLimiter:
    def __init__(self, max_per_second=2):  # 改为每秒控制而不是每分钟
        self.lock = threading.Lock()
        self.request_times = []
        self.max_per_second = max_per_second
        self.enabled = True  # 添加开关，允许完全禁用速率限制
        
    def wait_if_needed(self):
        """等待以确保不超过速率限制，使用更小的时间窗口"""
        if not self.enabled:
            return  # 如果禁用了速率限制，直接返回
            
        with self.lock:
            now = time.time()
            # 清理超过1秒的旧请求记录
            self.request_times = [t for t in self.request_times if now - t < 1]
            
            # 如果已达到每秒最大请求数，则等待
            if len(self.request_times) >= self.max_per_second:
                # 计算需要等待的时间 - 确保非常小
                wait_time = max(0, 1 - (now - self.request_times[0]))
                time.sleep(wait_time)
                
                # 更新当前时间并清理旧请求
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 1]
            
            # 记录本次请求时间
            self.request_times.append(now)

# 创建全局速率限制器 - 默认每秒2次请求，可通过命令行参数调整
rate_limiter = RateLimiter(max_per_second=2)

# 处理中断信号
def signal_handler(sig, frame):
    global running
    print("\n检测到中断信号，正在安全停止...")
    running = False

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)

def create_session():
    """创建一个带重试机制的请求会话"""
    session = requests.Session()
    
    # 配置重试策略 - 注意：对于429错误，我们不自动重试，而是手动处理
    retries = Retry(
        total=2,                # 减少重试次数
        backoff_factor=1,       # 增加退避因子
        status_forcelist=[500, 502, 503, 504],  # 不包括429，我们会手动处理
        allowed_methods=["GET"]
    )
    
    # 配置适配器
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    # 设置超时时间
    session.timeout = (5, 15)
    
    # 设置headers
    session.headers.update(headers)
    session.cookies.update(cookies)
    
    # 随机化User-Agent
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0'
    ]
    session.headers['User-Agent'] = random.choice(user_agents)
    
    return session

def check_username(username, session=None):
    """检查用户名是否可用，使用带重试机制的会话"""
    global rate_limiter, running
    
    params = {
        'value': username,
    }
    
    if session is None:
        session = create_session()
    
    # 使用速率限制器
    rate_limiter.wait_if_needed()
    
    try:
        response = session.get('https://github.com/signup_check/username', 
                              params=params, timeout=(5, 15))
        
        # 如果收到429，等待较短时间后重试
        if response.status_code == 429:
            # 获取等待时间，但设置上限为5秒，避免过长等待
            wait_time = min(5, int(response.headers.get('Retry-After', 5)))
            print(f"收到速率限制（429），等待 {wait_time} 秒...")
            
            # 降低请求速率
            rate_limiter.max_per_second = max(0.5, rate_limiter.max_per_second - 0.2)
            
            # 等待指定时间
            time.sleep(wait_time + random.uniform(0.1, 0.5))
            
            # 只有在程序仍在运行时才重试
            if running:
                # 创建新会话并重试
                new_session = create_session()
                rate_limiter.wait_if_needed()
                response = new_session.get('https://github.com/signup_check/username', 
                                       params=params, timeout=(5, 10))
        
        return response.status_code, response.text
    except Exception as e:
        print(f"检查用户名 {username} 时出错: {e}")
        # 如果是429错误，调整速率限制
        if "429" in str(e):
            print("检测到429错误，降低请求速率...")
            rate_limiter.max_per_second = max(0.5, rate_limiter.max_per_second - 0.2)
            time.sleep(random.uniform(2, 5))  # 减少冷却时间
        else:
            time.sleep(random.uniform(0.5, 1))  # 减少其他错误的等待时间
        return None, None

def process_username(username, pbar, output_file, progress_file):
    """处理单个用户名，用于在线程池中执行"""
    global running
    
    if not running:
        return False
    
    try:
        # 创建新会话
        session = create_session()
        
        # 大幅减少请求前延迟，改为0-0.1秒的极短延迟
        time.sleep(random.uniform(0, 0.1))
        
        status_code, response_text = check_username(username, session)
        
        if status_code == 200:
            print(f"找到可用用户名: {username}")
            
            # 使用锁确保文件写入的线程安全
            with file_lock:
                with open(output_file, 'a') as f:
                    f.write(f"{username}\n")
        
        # 记录已检查的用户名到进度文件
        with file_lock:
            with open(progress_file, 'a') as f:
                f.write(f"{username}\n")
        
        return True
    except Exception as e:
        print(f"处理用户名 {username} 时出错: {e}")
        return False
    finally:
        # 使用锁更新进度条
        with progress_lock:
            pbar.update(1)

def generate_usernames(start_username=None, end_username=None, length=4, max_workers=5, output_file="available_usernames.txt", batch_size=50):
    """
    生成从start_username到end_username的用户名组合，使用多线程检查
    默认从'aaaa'到'zzzz'检查所有4字母组合，使用更小的批次提高响应性
    
    参数:
        start_username: 起始用户名，如果为None则根据length生成 ('aaa'或'aaaa')
        end_username: 结束用户名，如果为None则根据length生成 ('zzz'或'zzzz')
        length: 用户名长度，3或4
        max_workers: 最大线程数
        output_file: 输出文件名
        batch_size: 批处理大小
    """
    global running, last_saved_progress
    
    # 设置默认的起始和结束用户名
    if length not in [3, 4]:
        raise ValueError("用户名长度只支持3或4")
    
    if start_username is None:
        start_username = 'a' * length
    if end_username is None:
        end_username = 'z' * length
    
    # 进度文件名
    progress_file = f"{output_file}.progress"
    
    chars = string.ascii_lowercase
    
    # 验证输入的用户名长度和字符有效性
    if len(start_username) != length or len(end_username) != length:
        raise ValueError(f"起始和结束用户名必须是{length}个字符")
    
    for char in start_username + end_username:
        if char not in chars:
            raise ValueError(f"无效字符: {char}，用户名只能包含小写字母a-z")
    
    # 计算起始和结束索引
    def username_to_index(username):
        base = len(chars)
        index = 0
        for i, char in enumerate(reversed(username)):
            char_index = chars.index(char)
            index += char_index * (base ** i)
        return index
    
    start_index = username_to_index(start_username)
    end_index = username_to_index(end_username)
    
    if start_index > end_index:
        raise ValueError("起始用户名必须在字母顺序上小于或等于结束用户名")
    
    # 生成用户名列表
    def index_to_username(index):
        base = len(chars)
        result = ""
        for _ in range(length):  # 使用传入的length代替硬编码的4
            char_index = index % base
            result = chars[char_index] + result
            index //= base
        return result
    
    # 查找已检查过的用户名
    checked_usernames = set()
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            checked_usernames = set(line.strip() for line in f)
        print(f"从进度文件加载了 {len(checked_usernames)} 个已检查的用户名")
    
    # 确保输出文件存在
    if not os.path.exists(output_file):
        open(output_file, 'a').close()
    
    usernames = []
    for i in range(start_index, end_index + 1):
        username = index_to_username(i)
        if username not in checked_usernames:
            usernames.append(username)
    
    total = len(usernames)
    print(f"将检查从 {start_username} 到 {end_username} 共 {total} 个用户名组合，批处理大小: {batch_size}")
    
    # 随机打乱用户名列表，避免按顺序检查
    random.shuffle(usernames)
    
    # 保留实时进度条  
    with tqdm(total=total, desc="检查用户名") as pbar:
        completed = 0
        
        # 分批处理用户名
        for i in range(0, len(usernames), batch_size):
            if not running:
                print("检测到中断请求，正在保存进度并退出...")
                break
                
            batch = usernames[i:i+batch_size]
            
            # 在批次之间添加非常短暂的随机延迟
            if i > 0:
                cooldown = random.uniform(0.05, 0.5)  # 进一步减少批次间等待时间
                print(f"\n批次间冷却: {cooldown:.2f} 秒...")
                time.sleep(cooldown)
            
            # 使用更安全的方式处理迷你批次，避免超时问题
            for mini_batch in [batch[j:j+max_workers] for j in range(0, len(batch), max_workers)]:
                # 这里不使用线程池，改为简单的线程列表，避免超时问题
                threads = []
                results = {}
                
                # 创建并启动线程
                for username in mini_batch:
                    thread = threading.Thread(
                        target=lambda u=username: results.update({u: process_username(u, pbar, output_file, progress_file)})
                    )
                    thread.daemon = True  # 设置为守护线程
                    threads.append(thread)
                    thread.start()
                
                # 等待所有线程完成，设置较短的超时时间，避免整体卡住
                for thread in threads:
                    # 最多等待20秒
                    thread.join(timeout=20)
                
                # 即使某些线程没完成也继续，记录完成的数量
                completed += len([r for r in results.values() if r])
                
                # 检查是否需要中断
                if not running:
                    break
                
                # 每个迷你批次之间添加极短的延迟
                time.sleep(random.uniform(0.01, 0.1))
                
                # 定期保存进度信息
                current_time = time.time()
                if current_time - last_saved_progress > progress_save_interval:
                    last_saved_progress = current_time
                    available = count_available_usernames(output_file)
                    print(f"\n进度更新: 已检查 {completed}/{total} 个用户名，找到 {available} 个可用用户名")
    
    # 计算找到的可用用户名数量
    available_count = count_available_usernames(output_file)
    
    return available_count

# 运行示例：
# python account.py --length 3 --start aaa --end zzz

def count_available_usernames(output_file):
    """计算已找到的可用用户名数量"""
    try:
        with open(output_file, 'r') as f:
            return len(f.readlines())
    except FileNotFoundError:
        return 0

if __name__ == "__main__":
    print("开始检查GitHub用户名是否可用...")
    
    # 添加命令行参数解析
    import argparse
    parser = argparse.ArgumentParser(description='检查GitHub用户名是否可用')
    parser.add_argument('--start', default=None, help='起始用户名 (默认根据长度自动设置)')
    parser.add_argument('--end', default=None, help='结束用户名 (默认根据长度自动设置)')
    parser.add_argument('--length', type=int, default=4, choices=[3, 4], help='用户名长度 (默认: 4)')
    parser.add_argument('--threads', type=int, default=5, help='线程数 (默认: 5)')
    parser.add_argument('--output', default='available_usernames.txt', help='输出文件名 (默认: available_usernames.txt)')
    parser.add_argument('--rate', type=float, default=2.0, help='每秒最大请求数 (默认: 2.0)')
    parser.add_argument('--batch-size', type=int, default=50, help='批处理大小 (默认: 50)')
    parser.add_argument('--no-limit', action='store_true', help='禁用速率限制 (风险高，可能导致IP被封)')
    args = parser.parse_args()
    
    # 设置速率限制
    rate_limiter.max_per_second = args.rate
    if args.no_limit:
        rate_limiter.enabled = False
        print("警告: 已禁用速率限制，请谨慎使用，可能导致IP被GitHub封禁")
    
    while True:
        try:
            # 可在这里调整线程数和起始/结束用户名
            available = generate_usernames(
                start_username=args.start,
                end_username=args.end,
                length=args.length,  # 传递用户名长度参数
                max_workers=args.threads,
                output_file=args.output,
                batch_size=args.batch_size
            )
            print(f"检查完成，找到 {available} 个可用的用户名。")
            print(f"可用用户名已保存到 {args.output} 文件中。")
            break  # 成功完成，退出循环
        
        except TimeoutError as e:
            print(f"警告: 检测到超时错误: {e}")
            print("降低请求速率和批处理大小后尝试继续...")
            # 动态降低速率和批处理大小
            args.rate = max(0.5, args.rate * 0.8)
            args.batch_size = max(10, int(args.batch_size * 0.8))
            args.threads = max(3, args.threads - 1)
            rate_limiter.max_per_second = args.rate
            print(f"新参数: 速率={args.rate:.1f}每秒, 批处理大小={args.batch_size}, 线程数={args.threads}")
            time.sleep(5)  # 休息一会再继续
            continue
            
        except KeyboardInterrupt:
            print("\n程序被用户中断")
            break
            
        except Exception as e:
            print(f"发生错误: {e}")
            print("等待10秒后尝试继续...")
            time.sleep(10)
            continue
