"""初始化管理员账户（一次性运行）"""
from app import create_app
from models.user import User
from utils.auth import hash_password
from extensions import db

app = create_app()

with app.app_context():
    # 检查是否已有 admin 账户
    existing = User.query.filter_by(username='admin').first()
    if existing:
        print(f'admin 账户已存在 (id={existing.id})，跳过创建')
    else:
        admin = User(
            username='admin',
            password_hash=hash_password('admin123'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print(f'admin 账户创建成功！用户名: admin, 密码: admin123')
