#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宿舍用电量监测脚本 - 生产级别
功能：定时查询剩余电量，低于阈值时发送邮件告警
"""

import json
import logging
import os
import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置区（支持环境变量覆盖） ====================

# Cookie 配置（需要定期手动更新）
USER_COOKIE = os.getenv("USER_COOKIE", "YOUR_COOKIE_HERE")

# 电量告警阈值（单位：度）
ELECTRICITY_THRESHOLD = float(os.getenv("ELECTRICITY_THRESHOLD", "20.0"))

# 查询间隔（单位：秒，默认1小时）
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))

# 邮箱配置
SMTP_CONFIG = {
    "server": os.getenv("SMTP_SERVER", "smtp.qq.com"),
    "port": int(os.getenv("SMTP_PORT", "465")),
    "use_ssl": os.getenv("SMTP_USE_SSL", "true").lower() == "true",
    "sender_email": os.getenv("SENDER_EMAIL", "your_email@qq.com"),
    "sender_password": os.getenv("SENDER_PASSWORD", "your_smtp_password"),
    "receiver_email": os.getenv("RECEIVER_EMAIL", "receiver@example.com"),
}

# 网络请求配置
REQUEST_CONFIG = {
    "timeout": 30,
    "max_retries": 3,
    "retry_delay": 5,
}

# 日志配置
def _get_log_path():
    """获取日志路径，兼容Docker和本地环境"""
    docker_path = "/app/logs/electricity_monitor.log"
    local_path = "electricity_monitor.log"
    if os.getenv("LOG_FILE"):
        return os.getenv("LOG_FILE")
    if os.path.exists("/app/logs"):
        return docker_path
    return local_path

LOG_CONFIG = {
    "level": logging.INFO,
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "file": _get_log_path(),
}

# ==================== 常量定义 ====================

API_URL = "http://sd.sontan.net/sdms-pay-weixin-gzzq/service/ammeterBalance?type=1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B)",
    "Referer": "http://sd.sontan.net/sdms-pay-weixin-gzzq/newWeixin/ele/eleInfo.html",
    "Connection": "keep-alive",
}


# ==================== 日志初始化 ====================

def setup_logging() -> logging.Logger:
    """配置日志系统"""
    logger = logging.getLogger("ElectricityMonitor")
    logger.setLevel(LOG_CONFIG["level"])
    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_CONFIG["level"])
    file_handler = logging.FileHandler(LOG_CONFIG["file"], encoding="utf-8")
    file_handler.setLevel(LOG_CONFIG["level"])
    formatter = logging.Formatter(LOG_CONFIG["format"])
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


logger = setup_logging()


# ==================== 网络请求模块 ====================

def create_session() -> requests.Session:
    """创建带重试机制的 Session"""
    session = requests.Session()
    retry_strategy = Retry(
        total=REQUEST_CONFIG["max_retries"],
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_electricity_data() -> Optional[Dict[str, Any]]:
    """请求接口获取电量数据"""
    headers = HEADERS.copy()
    headers["Cookie"] = USER_COOKIE
    session = create_session()
    try:
        logger.info("正在请求电量数据...")
        response = session.get(API_URL, headers=headers, timeout=REQUEST_CONFIG["timeout"])
        response.raise_for_status()
        data = response.json()
        logger.debug(f"原始响应数据: {data}")
        return data
    except requests.exceptions.Timeout:
        logger.error("请求超时，请检查网络连接")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("网络连接错误，请检查网络状态")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP错误: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        return None
    except Exception as e:
        logger.error(f"未知错误: {e}")
        return None
    finally:
        session.close()


# ==================== 数据解析模块 ====================

class ElectricityData:
    """电量数据模型"""
    def __init__(self, left_ele: float, left_money: float, ele_price: float, 
                 mon_time: int, left_free_ele: float = 0.0):
        self.left_ele = left_ele
        self.left_money = left_money
        self.ele_price = ele_price
        self.mon_time = mon_time
        self.left_free_ele = left_free_ele

    @property
    def query_time(self) -> str:
        return datetime.fromtimestamp(self.mon_time / 1000).strftime("%Y-%m-%d %H:%M:%S")

    def __str__(self) -> str:
        return (f"剩余电量: {self.left_ele}度 | 剩余金额: ¥{self.left_money} | "
                f"电价: ¥{self.ele_price}/度 | 查询时间: {self.query_time}")


def parse_electricity_data(raw_data: Dict[str, Any]) -> Optional[ElectricityData]:
    """解析接口返回的JSON数据"""
    try:
        status_code = raw_data.get("statusCode")
        if status_code != "200":
            message = raw_data.get("message", "未知错误")
            logger.error(f"接口返回异常状态: {status_code}, 消息: {message}")
            if "登录" in message or "session" in message.lower() or "token" in message.lower():
                logger.critical("Cookie可能已失效，请更新USER_COOKIE配置！")
            return None
        result = raw_data.get("resultObject")
        if not result:
            logger.error("响应数据缺少resultObject字段")
            return None
        electricity_data = ElectricityData(
            left_ele=float(result.get("leftEle", 0)),
            left_money=float(result.get("leftMoney", 0)),
            ele_price=float(result.get("elePrice", 0)),
            mon_time=int(result.get("monTime", 0)),
            left_free_ele=float(result.get("leftFreeEle", 0)),
        )
        logger.info(f"数据解析成功: {electricity_data}")
        return electricity_data
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"数据解析失败: {e}")
        return None


# ==================== 邮件告警模块 ====================

class EmailAlert:
    """邮件告警服务"""
    def __init__(self, config: Dict[str, Any]):
        self.server = config["server"]
        self.port = config["port"]
        self.use_ssl = config["use_ssl"]
        self.sender = config["sender_email"]
        self.password = config["sender_password"]
        self.receiver = config["receiver_email"]
        self.cooldown = 3600 * 6
        self.last_alert_time: Optional[float] = None

    def _can_send_alert(self) -> bool:
        if self.last_alert_time is None:
            return True
        return (time.time() - self.last_alert_time) > self.cooldown

    def send_low_electricity_alert(self, data: ElectricityData) -> bool:
        if not self._can_send_alert():
            logger.info("告警冷却中，跳过本次邮件发送")
            return False
        subject = f"⚠️ 宿舍电量告警 - 仅剩 {data.left_ele} 度"
        body = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.alert-header {{ background: #ff4757; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
.alert-body {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 8px 8px; }}
.warning {{ color: #ff4757; font-size: 24px; font-weight: bold; }}
</style></head><body><div class="container">
<div class="alert-header"><h2>⚡ 宿舍电量不足告警</h2></div>
<div class="alert-body">
<p class="warning">当前剩余电量: {data.left_ele} 度</p>
<p>电量已低于预设阈值 ({ELECTRICITY_THRESHOLD} 度)，请尽快充值！</p>
<p>剩余金额: ¥{data.left_money} | 电价: ¥{data.ele_price}/度</p>
<p>查询时间: {data.query_time}</p>
<p style="font-size:12px;color:#999;margin-top:20px;">此邮件由宿舍电量监测脚本自动发送，6小时内不会重复告警。</p>
</div></div></body></html>'''
        return self._send_email(subject, body, is_html=True)

    def send_error_alert(self, error_message: str) -> bool:
        if not self._can_send_alert():
            return False
        subject = "❌ 电量监测脚本运行异常"
        body = f"<h2>脚本运行异常</h2><p>错误信息: {error_message}</p><p>时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        return self._send_email(subject, body, is_html=True)

    def _send_email(self, subject: str, body: str, is_html: bool = False) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = self.receiver
            content_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))
            logger.info(f"正在发送邮件到 {self.receiver}...")
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.server, self.port) as server:
                    server.login(self.sender, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.server, self.port) as server:
                    server.starttls()
                    server.login(self.sender, self.password)
                    server.send_message(msg)
            self.last_alert_time = time.time()
            logger.info("邮件发送成功！")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("邮箱认证失败，请检查邮箱账号和授权码")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"邮件发送失败: {e}")
            return False
        except Exception as e:
            logger.error(f"发送邮件时发生未知错误: {e}")
            return False


# ==================== 监控核心逻辑 ====================

class ElectricityMonitor:
    """电量监控主类"""
    def __init__(self):
        self.email_alert = EmailAlert(SMTP_CONFIG)
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5

    def check_once(self) -> bool:
        logger.info("=" * 50)
        logger.info("开始执行电量检查...")
        raw_data = fetch_electricity_data()
        if raw_data is None:
            self.consecutive_failures += 1
            logger.warning(f"数据获取失败，连续失败次数: {self.consecutive_failures}")
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.email_alert.send_error_alert(f"连续 {self.consecutive_failures} 次获取数据失败")
            return False
        electricity_data = parse_electricity_data(raw_data)
        if electricity_data is None:
            self.consecutive_failures += 1
            logger.warning(f"数据解析失败，连续失败次数: {self.consecutive_failures}")
            return False
        self.consecutive_failures = 0
        if electricity_data.left_ele < ELECTRICITY_THRESHOLD:
            logger.warning(f"电量不足！当前: {electricity_data.left_ele}度，阈值: {ELECTRICITY_THRESHOLD}度")
            self.email_alert.send_low_electricity_alert(electricity_data)
        else:
            logger.info(f"电量正常: {electricity_data.left_ele}度 (阈值: {ELECTRICITY_THRESHOLD}度)")
        return True

    def run(self):
        logger.info("=" * 50)
        logger.info("宿舍电量监测脚本启动")
        logger.info(f"检查间隔: {CHECK_INTERVAL}秒 ({CHECK_INTERVAL/3600:.1f}小时)")
        logger.info(f"告警阈值: {ELECTRICITY_THRESHOLD}度")
        logger.info("=" * 50)
        self.check_once()
        while True:
            try:
                next_check = datetime.now().timestamp() + CHECK_INTERVAL
                next_check_str = datetime.fromtimestamp(next_check).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"下次检查时间: {next_check_str}")
                time.sleep(CHECK_INTERVAL)
                self.check_once()
            except KeyboardInterrupt:
                logger.info("收到中断信号，程序退出")
                break
            except Exception as e:
                logger.error(f"主循环发生异常: {e}")
                time.sleep(60)


# ==================== 程序入口 ====================

def validate_config() -> bool:
    errors = []
    if USER_COOKIE == "YOUR_COOKIE_HERE":
        errors.append("请配置 USER_COOKIE")
    if SMTP_CONFIG["sender_email"] == "your_email@qq.com":
        errors.append("请配置 sender_email")
    if SMTP_CONFIG["sender_password"] == "your_smtp_password":
        errors.append("请配置 sender_password")
    if SMTP_CONFIG["receiver_email"] == "receiver@example.com":
        errors.append("请配置 receiver_email")
    if errors:
        logger.error("配置验证失败:")
        for error in errors:
            logger.error(f"  - {error}")
        return False
    return True


def main():
    print("""
    ╔═══════════════════════════════════════════════╗
    ║       宿舍用电量监测脚本 v1.0                  ║
    ║       Electricity Monitor                     ║
    ╚═══════════════════════════════════════════════╝
    """)
    if not validate_config():
        logger.error("请先完成配置后再运行脚本")
        return
    monitor = ElectricityMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
