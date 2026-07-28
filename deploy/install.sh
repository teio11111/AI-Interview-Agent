#!/bin/bash
# ============================================
# AI-Interview-Agent 一键部署脚本
# 用法：sudo bash install.sh
# ============================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo "  AI-Interview-Agent 一键部署 (v2.0)"
echo "=========================================="
echo "[1/7] 当前目录: $PROJECT_DIR"

# ---------- 2. 系统依赖 ----------
echo "[2/7] 安装系统依赖（python3-venv, gcc, mysql-client）..."
if command -v apt &>/dev/null; then
    sudo apt update -qq
    sudo apt install -y python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config
elif command -v yum &>/dev/null; then
    sudo yum install -y python3-devel gcc mysql-devel pkg-config
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-devel gcc mysql-devel pkg-config
fi

# ---------- 3. venv ----------
echo "[3/7] 创建虚拟环境 venv/ ..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q

# ---------- 4. 装依赖 ----------
echo "[4/7] 装依赖（requirements_full.txt）..."
pip install -r requirements_full.txt -q

# ---------- 5. .env ----------
echo "[5/7] 配置 .env ..."
if [ ! -f "../.env" ]; then
    cp .env.production ../.env
    echo "  ✅ 已从 .env.production 复制 .env，请编辑 .env 填真实密钥："
    echo "     - SECRET_KEY（用 openssl rand -hex 32 生成）"
    echo "     - LLM_API_KEY（MiniMax-M3）"
    echo "     - XFYUN_* / TENCENT_*（讯飞 / 腾讯云）"
    echo "     - DB_PASSWORD（宝塔面板里查）"
    echo ""
    read -p "  是否现在编辑 .env? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} ../.env
    fi
else
    echo "  ⚠️  .env 已存在，本脚本不动它（手动跑 deploy/UPLOAD_GUIDE.md 里的配置核对）"
    echo "  如要重置：rm ../.env 后再跑本脚本"
fi

# ---------- 6. 关 DEBUG + 创 admin ----------
echo "[6/7] 关 DEBUG + 初始化 admin 账号 ..."
cd "$PROJECT_DIR/.."
# v2.0 调整：DEBUG 不在 config.py 里，在 app.py:86 的 socketio.run() 里
if [ -f "app.py" ]; then
    sed -i 's/socketio.run(app, host=.*port=8088, debug=True/socketio.run(app, host='"'"'0.0.0.0'"'"', port=8088, debug=False/' app.py
    echo "  已检查 app.py:86（v2.0 socketio.run debug 标记）"
    grep "socketio.run" app.py | head -1
fi
# 兼容 v1.0 老配置（如果 config.py 存在也改下）
if [ -f "config/config.py" ]; then
    sed -i 's/DEBUG = True/DEBUG = False/' config/config.py
    echo "  已同步修改 config/config.py"
fi

# ---------- 7. 起始启动 + 跑 init_admin ----------
echo "[7/7] 初次启动 + 建表 + 建 admin ..."
cd "$PROJECT_DIR/.."
# 先跑一次 app.py 让 create_all 建表
python3 app.py &
BOOT_PID=$!
sleep 8
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