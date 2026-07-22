# AI-Interview-Agent 云端部署手册（手动版）

> 数据库已建好，下面只做「代码上传 + 启动」。

---

## 0. 服务器前置检查（一次）

```bash
# 0.1 确认 Python 版本（要 3.10+，你的是 3.12.3 ✅）
python3 --version

# 0.2 确认 MySQL 在跑（要 8.0+）
mysql --version
sudo systemctl status mysql
# 如果没装：宝塔面板 → 软件商店 → 搜 MySQL 8.0 → 安装

# 0.3 确认 ai_interview_prod 库存在
mysql -uai_app -p'AppProd@2026' ai_interview_prod -e "SELECT DATABASE();"
# 看到 ai_interview_prod 说明建好了

# 0.4 确认 8088 端口空闲
ss -tlnp | grep 8088
# 没输出就是空闲的
```

---

## 1. 上传项目到服务器

### 1.1 本地打包（PowerShell）

```powershell
# 把整个项目打 zip（deploy/ 子目录会自动带上）
Compress-Archive -Path "c:\Users\Teio\Desktop\AI-Interview-Agent\*" `
  -DestinationPath "c:\Users\Teio\Desktop\AI-Interview-Agent\deploy.zip" `
  -Exclude "__pycache__",".git","*.log","_*.py",".env","flask.err","flask.log","smoke_*.png"
```

### 1.2 Xftp 上传

```
本机:    C:\Users\Teio\Desktop\AI-Interview-Agent\deploy.zip
服务器:  /home/steve/ai-interview.zip
```

### 1.3 Xshell 解压

```bash
cd /home/steve
unzip -o ai-interview.zip -d ai-interview
cd ai-interview
ls -la deploy/
```

---

## 2. 一键部署

```bash
cd /home/steve/ai-interview/deploy
chmod +x *.sh
sudo bash install.sh
```

`install.sh` 会自动：
1. 装系统依赖（python3-venv, gcc, mysql-client）
2. 建 venv
3. 装依赖（requirements_full.txt）
4. 复制 `.env.production` → `.env`（**会让你填密钥**）
5. 关 DEBUG
6. 跑 init_admin.py 建 admin 账号（admin / admin123，**部署完请改密码**）

---

## 3. 改 .env 填密钥（必做）

```bash
cd /home/steve/ai-interview
nano .env
# 至少要填这几项：
#   SECRET_KEY  →  openssl rand -hex 32
#   LLM_API_KEY →  DeepSeek 真实 key
#   XFYUN_*     →  讯飞真实 key
#   TENCENT_*   →  腾讯云真实 key
```

---

## 4. 启动 + 验证

```bash
cd /home/steve/ai-interview
bash deploy/start.sh
# 输出应该是：
#   ✅ 已启动  PID=xxxxx
#   访问: http://服务器内网IP:8088/login

# 浏览器打开上面的地址，用 admin / admin123 登录
```

---

## 5. 日常运维命令

```bash
cd /home/steve/ai-interview

bash deploy/start.sh    # 启动
bash deploy/stop.sh     # 停止
bash deploy/restart.sh  # 重启
bash deploy/log.sh      # 看实时日志（Ctrl+C 退出）

# 或者直接看日志
tail -f flask.log
```

---

## 常见坑速查

| 报错 | 解决 |
|------|------|
| `pymysql.err.OperationalError: (1045)` Access denied | 密码不对，检查 `.env` 里的 `DB_PASSWORD` 跟建库时一致 |
| `pymysql.err.OperationalError: (2003)` Can't connect | `DB_HOST` 用 `localhost`（不要 `127.0.0.1`） |
| `pymysql.err.OperationalError: (1049)` Unknown database | 库没建好，重新跑 mysql 客户端确认 |
| `ModuleNotFoundError: No module named 'flask_socketio'` | 漏装，重新跑 `pip install -r requirements_full.txt` |
| Flask-SocketIO 启动报 werkzeug 错 | 确认 `app.py` 最后一行有 `allow_unsafe_werkzeug=True` |
| 端口 8088 已占用 | `ss -tlnp \| grep 8088` 看 PID，杀掉或换端口 |
| admin 账号已存在 | `init_admin.py` 自动跳过，直接用 |

---

## 文件清单（deploy/ 目录下）

```
deploy/
├── requirements_full.txt   # 完整依赖（Flask + Flask-SocketIO + 讯飞 + 腾讯云 + 文档解析等）
├── .env.production         # 生产环境变量模板（不含真密钥）
├── install.sh              # 一键部署（venv + pip + init_admin）
├── start.sh                # 后台启动 Flask
├── stop.sh                 # 停止 Flask
├── restart.sh              # 重启 Flask
├── log.sh                  # 看实时日志
├── create_database.sh      # 【备用】MySQL 建库脚本（你已建好可不跑）
└── UPLOAD_GUIDE.md         # 本文档
```