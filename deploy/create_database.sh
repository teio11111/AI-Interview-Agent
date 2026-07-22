#!/bin/bash
# ============================================
# 云端 MySQL 建库脚本（备用，你已经建好可以跳过）
# 用法：sudo bash create_database.sh
# ============================================
set -e

DB_NAME="ai_interview_prod"
DB_USER="ai_app"
DB_PASS="AppProd@2026"

echo "=========================================="
echo "  云端 MySQL 建库"
echo "=========================================="
echo "  库名:   $DB_NAME"
echo "  用户:   $DB_USER"
echo "  密码:   $DB_PASS"
echo "=========================================="

mysql -uroot -p <<EOF
CREATE DATABASE IF NOT EXISTS ${DB_NAME} DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SHOW DATABASES LIKE '${DB_NAME}';
SELECT user, host FROM mysql.user WHERE user='${DB_USER}';
EOF

echo ""
echo "✅ 完成！测试连接："
echo "   mysql -u${DB_USER} -p'${DB_PASS}' ${DB_NAME} -e 'SELECT DATABASE();'"