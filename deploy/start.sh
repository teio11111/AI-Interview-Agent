#!/bin/bash
# 启动 Flask（后台，nohup）
cd "$(dirname "$0")"
cd ..

# 已经在跑就提示
if ss -tlnp 2>/dev/null | grep -q ":8088"; then
    echo "⚠️  端口 8088 已被占用，先跑 stop.sh 再启动"
    ss -tlnp | grep ":8088"
    exit 1
fi

# 仅设置项目进程时区，不改服务器全局配置
export TZ=Asia/Shanghai

source venv/bin/activate
nohup python3 app.py > flask.log 2>&1 &
echo $! > deploy/flask.pid
sleep 6

if ss -tlnp 2>/dev/null | grep -q ":8088"; then
    echo "✅ 已启动  PID=$(cat deploy/flask.pid)"
    echo "   端口: $(ss -tlnp | grep ':8088' | awk '{print $4}')"
    echo "   日志: tail -f flask.log"
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "$IP" ] && IP="<服务器IP>"
    echo "   访问: http://${IP}:8088/login"
else
    echo "❌ 启动失败，看 flask.log 排查"
    tail -30 flask.log
fi