# -*- coding: utf-8 -*-
"""初始化 MySQL：建库建表 + 创建专用账号（幂等，可重复运行）"""
import json, os, subprocess, secrets, sys

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, 'config.json')

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print('CMD FAIL:', ' '.join(cmd))
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        raise SystemExit(1)
    return r.stdout

def main():
    root_pw = os.environ.get('MYSQL_ROOT_PW', '')
    db_password = secrets.token_hex(16)

    # 用 root 建库建表（root 无密码 or 提供密码）
    env = dict(os.environ)
    args = ['mysql', '-u', 'root']
    if root_pw:
        args += ['-p' + root_pw]
    with open(os.path.join(BASE, 'schema.sql'), encoding='utf-8') as f:
        sql = f.read()
    sql += '\nCREATE USER IF NOT EXISTS \'miaoda\'@\'localhost\' IDENTIFIED BY \'%s\';\nGRANT ALL PRIVILEGES ON miaoda_db.* TO \'miaoda\'@\'localhost\';\nFLUSH PRIVILEGES;\n' % db_password
    r = subprocess.run(args, input=sql, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print('mysql init failed:', r.stderr[-1000:])
        raise SystemExit(1)

    cfg = {
        'db_host': '127.0.0.1',
        'db_port': 3306,
        'db_user': 'miaoda',
        'db_password': db_password,
        'db_name': 'miaoda_db',
        'port': 5000
    }
    with open(CFG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print('OK: 数据库 miaoda_db 与账号 miaoda 已就绪，配置写入', CFG_PATH)

if __name__ == '__main__':
    main()
