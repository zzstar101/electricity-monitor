# 宿舍电量监测脚本

定时查询宿舍剩余电量，低于阈值时发送邮件告警。

## 功能特性

- ⏰ 每小时自动查询电量
- ⚡ 低电量邮件告警（默认阈值 20 度）
- 🔄 告警冷却机制（6小时内不重复告警）
- 🛡️ 高鲁棒性（网络重试、异常处理、Cookie失效检测）
- 🐳 支持 Docker 部署

## 快速开始

### Docker 部署（推荐）

1. 修改 `docker-compose.yml` 中的配置：
   - `USER_COOKIE`: 你的 Cookie
   - `SENDER_EMAIL`: 发件邮箱
   - `SENDER_PASSWORD`: 邮箱授权码
   - `RECEIVER_EMAIL`: 收件邮箱

2. 启动服务：
```bash
docker-compose up -d --build
```

3. 查看日志：
```bash
docker logs -f electricity-monitor
```

### 本地运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 修改 `electricity_monitor.py` 中的配置

3. 运行：
```bash
python electricity_monitor.py
```

## 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| USER_COOKIE | 学校系统Cookie | - |
| ELECTRICITY_THRESHOLD | 告警阈值(度) | 20 |
| CHECK_INTERVAL | 检查间隔(秒) | 3600 |
| SMTP_SERVER | SMTP服务器 | smtp.qq.com |
| SMTP_PORT | SMTP端口 | 465 |
| SMTP_USE_SSL | 使用SSL | true |
| SENDER_EMAIL | 发件邮箱 | - |
| SENDER_PASSWORD | 邮箱授权码 | - |
| RECEIVER_EMAIL | 收件邮箱 | - |

## 常用命令

```bash
# 查看日志
docker logs -f electricity-monitor

# 重启服务
docker restart electricity-monitor

# 停止服务
docker-compose down

# 更新并重启
docker-compose up -d --build
```

## License

MIT
