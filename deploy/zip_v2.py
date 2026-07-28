"""一键打包脚本 v2 - 用 Python zipfile 实现，跨平台稳定"""
import os
import zipfile
import datetime

PROJECT_ROOT = r'C:\Users\Teio\Desktop\AI-Interview-Agent'
DESKTOP = os.path.join(os.path.expanduser('~'), 'Desktop')

# 排除规则
EXCLUDE_DIRS = {'__pycache__', '.git', 'venv', '.venv', 'env', '.idea', '.vscode', 'node_modules'}
EXCLUDE_FILES = {'.env', 'flask.err', 'flask.log', 'app.log', 'app.err.log',
                 'deploy.zip', 'deploy_lastest.zip', 'ai-interview_*.zip',
                 'cookies.txt', 'login.json', 'check_cands.png',
                 'dashboard_top.png', 'login_page.png', 'pdf_upload_modal.png'}
EXCLUDE_GLOBS = ['_*.py', '_*.txt', '_*.png', 'test_*.png', 'test_*.py',
                 '*.pyc', '*.pyo', '*.log', '*.bak',
                 'DGT-java*.pdf', 'Java工程师岗位JD.pdf', '*岗位JD.pdf', '*一面*.pdf']

import fnmatch

def is_excluded(name):
    """检查文件名是否匹配排除规则"""
    # __init__.py 等 Python 包标识文件永远不排除
    if name == '__init__.py':
        return False
    # 直接文件名
    if name in EXCLUDE_FILES:
        return True
    # glob 匹配
    for pattern in EXCLUDE_GLOBS:
        if fnmatch.fnmatch(name, pattern):
            return True
    # 通配符匹配 deploy/ai-interview_*.zip
    if fnmatch.fnmatch(name, 'ai-interview_*.zip'):
        return True
    return False

def is_excluded_dir(name):
    return name in EXCLUDE_DIRS or name.startswith('.')

def main():
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_name = f'ai-interview_{timestamp}.zip'
    zip_path = os.path.join(DESKTOP, zip_name)

    print(f'▶ 开始打包 → {zip_name}')
    print(f'  项目根目录: {PROJECT_ROOT}')

    count = 0
    total_size = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # 过滤目录
            dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
            for f in files:
                if is_excluded(f):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, PROJECT_ROOT)
                zf.write(full, rel)
                count += 1
                total_size += os.path.getsize(full)

    zip_size = os.path.getsize(zip_path)
    print(f'  ✅ 打包完成: {zip_path}')
    print(f'  ✅ 文件数: {count}')
    print(f'  ✅ 原始大小: {total_size/1024/1024:.2f} MB')
    print(f'  ✅ 压缩后: {zip_size/1024/1024:.2f} MB')
    print(f'  ✅ 压缩率: {(1-zip_size/total_size)*100:.1f}%')

    # 备份到项目根目录
    backup = os.path.join(PROJECT_ROOT, 'deploy_lastest.zip')
    import shutil
    shutil.copy(zip_path, backup)
    print(f'  ✅ 项目内备份: deploy_lastest.zip')

    print()
    print('=' * 50)
    print('  🎉 打包完成！')
    print('=' * 50)
    print()
    print('接下来你可以：')
    print('  1. 自动弹出 Desktop 文件夹')
    print('  2. 把 zip 拖到 Xftp 上传到服务器')
    print('  3. 服务器跑 install.sh + 启动')

    # 自动弹出文件夹
    try:
        os.startfile(os.path.dirname(zip_path))
    except:
        pass

if __name__ == '__main__':
    main()