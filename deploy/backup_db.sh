#!/bin/bash
# 每日自动备份 MySQL 数据库
BACKUP_DIR=/home/steve/ai-interview/backups
DATE=$(date +%Y%m%d_%H%M%S)
mysqldump -h 127.0.0.1 --no-tablespaces -u ai_interview_agent -pq12345678 ai_interview_agent > ${BACKUP_DIR}/ai_interview_${DATE}.sql
# 只保留最近7天的备份
find ${BACKUP_DIR} -name '*.sql' -mtime +7 -delete
echo "[${DATE}] backup done" >> ${BACKUP_DIR}/backup.log
