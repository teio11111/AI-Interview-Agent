#!/bin/bash
# ============================================
# AI-Interview-Agent 一键部署脚本
# 用法：sudo bash install.sh
# ============================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo "  AI-Interview-Agent 一键部署"
echo "=========================================="
echo "[1/6] 当前目录: $PROJECT_DIR"

# ---------- 2. 系统依赖 ----------
echo "[2/6] 安装系统依赖（python3-venv, gcc, mysql-client）..."
if command -v apt &>/dev/null; then
    sudo apt update -qq
    sudo apt install -y python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config
elif command -v yum &>/dev/null; then
    sudo yum install -y python3-devel gcc mysql-devel pkg-config
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-devel gcc mysql-devel pkg-config
fi

# ---------- 3. venv ----------
echo "[3/6] 创建虚拟环境 venv/ ..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q

# ---------- 4. 装依赖 ----------
echo "[4/6] 装依赖（requirements_full.txt）..."
pip install -r requirements_full.txt -q

# ---------- 5. .env ----------
echo "[5/6] 配置 .env ..."
if [ ! -f "../.env" ]; then
    cp .env.production ../.env
    echo "  ⚠️  已从 .env.production 复制 .env，请编辑 .env 填真实密钥："
    echo "     - SECRET_KEY（用 openssl rand -hex 32 生成）"
    echo "     - LLM_API_KEY（DeepSeek）"
    echo "     - XFYUN_* / TENCENT_*（讯飞 / 腾讯云）"
    echo ""
    read -p "  是否现在编辑 .env? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} ../.env
    fi
else
    echo "  .env 已存在，跳过"
fi

# ---------- 6. 关 DEBUG + 创 admin ----------
echo "[6/6] 关 DEBUG + 初始化 admin 账号 ..."
cd "$PROJECT_DIR/.."
sed -i 's/DEBUG = True/DEBUG = False/' config/config.py
grep "DEBUG" config/config.py

# 先跑一次 app.py 让 create_all 建表
python3 app.py &
BOOT_PID=$!
sleep 5
kill $BOOT_PID 2>/dev/null || true
sleep 1

python3 init_admin.py

echo ""
echo "=========================================="
echo "  ✅ 部署完成！"
echo "=========================================="
echo "启动:  bash deploy/start.sh"
echo "停止:  bash deploy/stop.sh"
echo "日志:  bash deploy/log.sh"
echo ""