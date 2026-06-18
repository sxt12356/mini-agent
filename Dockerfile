ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG NO_PROXY

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 先复制 requirements，利用 Docker build cache
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# 再复制业务代码
COPY . /app

# 日志目录
RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
