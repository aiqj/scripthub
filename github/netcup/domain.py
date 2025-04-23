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
import argparse

# 全局变量和常量
lowercase_letters = string.ascii_lowercase  # 'abcdefghijklmnopqrstuvwxyz'
file_lock = threading.Lock()  # 线程锁，用于文件写入
progress_lock = threading.Lock()  # 锁，用于进度条更新
running = True  # 全局运行状态
last_saved_progress = 0  # 上次保存进度的时间
progress_save_interval = 60  # 每60秒保存一次进度
progress_file = "domain_progress.txt"  # 进度文件
output_file = "available_domains.txt"  # 输出文件名


# 全局速率限制器
class RateLimiter:
    def __init__(self, max_per_second=2):
        self.lock = threading.Lock()
        self.request_times = []
        self.max_per_second = max_per_second
        self.enabled = True

    def wait_if_needed(self):
        if not self.enabled:
            return
        with self.lock:
            now = time.time()
            self.request_times = [t for t in self.request_times if now - t < 1]
            if len(self.request_times) >= self.max_per_second:
                wait_time = max(0, 1 - (now - self.request_times[0]))
                time.sleep(wait_time)
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 1]
            self.request_times.append(now)

    def adjust_rate(self, increase=False):
        with self.lock:
            if increase:  # 遇到错误时降低速率
                self.max_per_second = max(0.5, self.max_per_second - 0.2)
            else:  # 成功请求后逐步增加速率
                if len(self.request_times) % 10 == 0:  # 每10个成功请求
                    self.max_per_second = min(2, self.max_per_second + 0.2)


rate_limiter = RateLimiter(max_per_second=2)


def signal_handler(sig, frame):
    global running
    print("\n检测到中断信号，正在安全停止...")
    running = False


signal.signal(signal.SIGINT, signal_handler)


def create_session():
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    session.timeout = (5, 15)
    return session


def username_to_index(username, length):
    """将域名字符串转换为数字索引，考虑指定长度"""
    base = len(lowercase_letters)
    index = 0
    if len(username) != length:
        raise ValueError(f"字符串长度必须为{length}")
    for i, char in enumerate(reversed(username)):
        if char not in lowercase_letters:
            raise ValueError("字符串必须只包含小写字母")
        char_index = lowercase_letters.index(char)
        index += char_index * (base ** i)
    return index


def index_to_username(index, length):
    """将数字索引转换为域名字符串，指定长度"""
    base = len(lowercase_letters)
    result = ""
    for _ in range(length):
        char_index = index % base
        result = lowercase_letters[char_index] + result
        index //= base
    return result


def generate_combinations(start_str=None, end_str=None, length=4):
    """生成指定范围内的组合列表"""
    if start_str is None:
        start_str = 'a' * length  # 默认起始：length个'a'
    else:
        if len(start_str) != length or not all(c in lowercase_letters for c in start_str):
            raise ValueError(f"起始字符串必须是{length}个小写字母")

    if end_str is None:
        end_str = 'z' * length  # 默认结束：length个'z'
    else:
        if len(end_str) != length or not all(c in lowercase_letters for c in end_str):
            raise ValueError(f"结束字符串必须是{length}个小写字母")

    if username_to_index(start_str, length) > username_to_index(end_str, length):
        raise ValueError("起始字符串必须在字母顺序上小于或等于结束字符串")

    start_index = username_to_index(start_str, length)
    end_index = username_to_index(end_str, length)

    combinations = [index_to_username(i, length) for i in range(start_index, end_index + 1)]
    return combinations


def check_domain(combo, pbar, length):
    global running, rate_limiter
    if not running:
        return

    domain_name = combo  # 现在combo是字符串，如"aa" for length=2
    if len(domain_name) != length:
        return  # 确保长度正确（虽然生成时已验证）

    data = {'name': domain_name, 'tld': 'de'}

    rate_limiter.wait_if_needed()
    time.sleep(random.uniform(0, 0.1))  # 随机延迟

    try:
        session = create_session()
        response = session.post('https://www.netcup.com/api/shop/domains/check', json=data, timeout=10)

        if response.status_code == 200:
            try:
                result = response.json()
                if result.get('success') and result.get('status') == 'free':
                    full_domain = f"{domain_name}.de"
                    print(full_domain)  # 仅打印可用的域名
                    with file_lock:  # 线程安全写入
                        with open(output_file, 'a') as f:
                            f.write(full_domain + '\n')  # 立即写入文件
                    rate_limiter.adjust_rate()  # 成功请求，调整速率
            except Exception:
                pass
        elif response.status_code in [417, 429]:
            rate_limiter.adjust_rate(increase=True)  # 降低速率
            wait_time = min(5, int(response.headers.get('Retry-After', 5)))
            time.sleep(wait_time + random.uniform(0.1, 0.5))
            if running:
                return check_domain(combo, pbar, length)  # 重试
    except Exception:
        pass  # 静默处理

    with progress_lock:
        pbar.update(1)
    with file_lock:
        if time.time() - last_saved_progress > progress_save_interval:
            last_saved_progress = time.time()
            with open(progress_file, 'a') as f:
                f.write(f"{domain_name}\n")  # 保存进度


def main():
    global running
    args = parse_args()
    rate_limiter.max_per_second = args.rate

    # 清空输出文件，确保从空白开始
    with file_lock:
        with open(output_file, 'w') as f:
            pass  # 打开并关闭以清空文件

    combinations = generate_combinations(args.start, args.end, args.length)  # 生成指定范围的组合
    total = len(combinations)
    print(
        f"将检查长度为{args.length}的域名，从 {args.start or ('a' * args.length)} 到 {args.end or ('z' * args.length)} 共 {total} 个组合")

    with tqdm(total=total, desc="查询进度") as pbar:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = [executor.submit(check_domain, combo, pbar, args.length) for combo in combinations]
            for future in as_completed(futures):
                if not running:
                    break  # 如果中断，停止提交新任务

    print(f"查询过程已完成。可用的域名已实时写入 {output_file} 文件。")


def parse_args():
    parser = argparse.ArgumentParser(description='检查netcup域名可用性')
    parser.add_argument('--length', type=int, default=4, help='域名字符串长度 (例如: 2, 3, 4)，默认4')
    parser.add_argument('--start', default=None, help='起始域名 (例如: aa)')
    parser.add_argument('--end', default=None, help='结束域名 (例如: zz)')
    parser.add_argument('--rate', type=float, default=2.0, help='每秒最大请求数')
    parser.add_argument('--threads', type=int, default=5, help='最大线程数')
    return parser.parse_args()


if __name__ == "__main__":
    main()
