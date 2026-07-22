#!/bin/bash
# 重启 Flask
cd "$(dirname "$0")"
bash stop.sh
sleep 1
bash start.sh