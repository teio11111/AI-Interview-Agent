"""初始化多个面试官账号（v3.1）

用法：python init_users.py
默认创建 5 个面试官账号，密码统一为 123456，登录后各自修改。
"""
from app import create_app
from models.user import User
from utils.auth import hash_password
from extensions import db

# 要创建的账号列表（可自定义）
USERS = [
    {'username': 'admin1', 'password': '123456', 'role': 'admin'},
    {'username': 'admin2', 'password': '123456', 'role': 'admin'},
    {'username': 'admin3', 'password': '123456', 'role': 'admin'},
    {'username': 'admin4', 'password': '123456', 'role': 'admin'},
    {'username': 'admin5', 'password': '123456', 'role': 'admin'},
]

app = create_app()

with app.app_context():
    created = 0
    skipped = 0
    for u in USERS:
        existing = User.query.filter_by(username=u['username']).first()
        if existing:
            print(f'  [跳过] {u["username"]} 已存在 (id={existing.id})')
            skipped += 1
        else:
            user = User(
                username=u['username'],
                password_hash=hash_password(u['password']),
                role=u['role']
            )
            db.session.add(user)
            db.session.commit()
            print(f'  [创建] {u["username"]} / {u["password"]} (id={user.id})')
            created += 1

    # 汇总
    total = User.query.filter_by(role='admin').count()
    print(f'\n完成: 新建 {created} 个, 跳过 {skipped} 个, 当前共 {total} 个管理员账号')
