#!/bin/bash
# 云端增量更新脚本：只替换代码，不动 venv、.env、数据库
set -e

PROJECT_DIR=/home/steve/ai-interview
NEW_ZIP=/home/steve/ai-interview_new.zip
BACKUP_DIR=/home/steve/ai-interview_backup_$(date +%Y%m%d_%H%M%S)
TMP_DIR=/home/steve/ai-interview_new

echo "==========================================="
echo "  云端增量更新 (保留 venv/.env)"
echo "==========================================="

# 1. 停服务
echo "[1/6] 停止 Flask..."
cd "$PROJECT_DIR"
if [ -f deploy/stop.sh ]; then
    bash deploy/stop.sh || true
fi
sleep 2
# 二次清理
pkill -f "python3 app.py" 2>/dev/null || true
sleep 2
ss -tlnp 2>/dev/null | grep ':8088' && { echo "❌ 端口仍被占用"; exit 1; } || echo "  端口已释放"

# 2. 备份当前代码（不含 venv）
echo "[2/6] 备份当前代码到 $BACKUP_DIR ..."
mkdir -p "$BACKUP_DIR"
rsync -a --exclude='venv' --exclude='.env' --exclude='__pycache__' "$PROJECT_DIR/" "$BACKUP_DIR/"

# 3. 解压新 zip 到临时目录
echo "[3/6] 解压新代码到 $TMP_DIR ..."
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
unzip -q "$NEW_ZIP" -d "$TMP_DIR"
ls "$TMP_DIR" | head -10

# 4. 同步代码（保留 venv/.env/数据库配置）
echo "[4/6] 同步代码到 $PROJECT_DIR ..."
rsync -a --exclude='venv' --exclude='.env' --exclude='__pycache__' \
    "$TMP_DIR/" "$PROJECT_DIR/"

# 5. 清理临时
echo "[5/6] 清理临时目录 ..."
rm -rf "$TMP_DIR"
rm -f "$NEW_ZIP"

# 6. 启动服务
echo "[6/6] 启动 Flask..."
chmod +x deploy/*.sh
bash deploy/start.sh

echo "==========================================="
echo "  ✅ 更新完成！"
echo "  备份目录: $BACKUP_DIR"
echo "==========================================="