#!/bin/bash
# 看 Flask 实时日志
cd "$(dirname "$0")"
cd ..

if [ ! -f flask.log ]; then
    echo "⚠️  flask.log 不存在"
    exit 1
fi

echo "=========================================="
echo "  Flask 实时日志（Ctrl+C 退出）"
echo "=========================================="
tail -f flask.log