#!/bin/bash
# 停止 Flask
cd "$(dirname "$0")"
cd ..

PID=""
if [ -f deploy/flask.pid ]; then
    PID=$(cat deploy/flask.pid)
fi

# fallback：按端口找
if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    PID=$(ss -tlnp 2>/dev/null | grep ":8088" | grep -oP 'pid=\K[0-9]+' | head -1)
fi

if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
        echo "✅ 已强制停止 PID=$PID"
    else
        echo "✅ 已停止 PID=$PID"
    fi
    rm -f deploy/flask.pid
else
    echo "⚠️  端口 8088 没在监听"
fi