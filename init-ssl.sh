#!/bin/sh
# SSL 证书自动初始化脚本
# 如果证书目录为空, 生成自签名证书; 如果已有证书, 跳过
# 将真实证书放到 certs/ 目录即可覆盖

CERT_DIR="/home/zhuying/leadframe-inventory-system/certs"

if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
    echo "[ssl-init] 未找到 SSL 证书, 生成自签名证书..."
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$CERT_DIR/privkey.pem" \
        -out "$CERT_DIR/fullchain.pem" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
    echo "[ssl-init] 自签名证书已生成到 $CERT_DIR/"
    echo "[ssl-init] 生产环境请替换为真实证书:"
    echo "[ssl-init]   fullchain.pem - 证书链文件"
    echo "[ssl-init]   privkey.pem   - 私钥文件"
else
    echo "[ssl-init] 已找到 SSL 证书, 跳过生成"
fi
