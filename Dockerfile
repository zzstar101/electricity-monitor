FROM python:3.11-slim

LABEL maintainer="electricity-monitor"
LABEL description="宿舍电量监测服务"

WORKDIR /app

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY electricity_monitor.py .
RUN mkdir -p /app/logs

CMD ["python", "-u", "electricity_monitor.py"]
