# -*- coding: utf-8 -*-
"""妙搭小站 · 本机后端服务（Flask + MySQL）
账号注册/登录 + 全部游戏成绩上报 + 排行榜查询。
启动：python app.py  （默认 http://127.0.0.1:5000）
"""
import os, json, hashlib, secrets, datetime, traceback
from flask import Flask, request, jsonify, g
import pymysql

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, 'config.json')

def load_cfg():
    with open(CFG_PATH, encoding='utf-8') as f:
        return json.load(f)

CFG = load_cfg()
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

def db():
    if 'db' not in g:
        g.db = pymysql.connect(
            host=CFG.get('db_host', '127.0.0.1'),
            port=CFG.get('db_port', 3306),
            user=CFG['db_user'], password=CFG['db_password'],
            database=CFG['db_name'], charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor, autocommit=True)
    return g.db

@app.teardown_appcontext
def close_db(exc):
    d = g.pop('db', None)
    if d is not None:
        try: d.close()
        except Exception: pass

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt.encode('utf-8'), 120000).hex()

def make_token():
    return secrets.token_hex(32)

def auth_user():
    h = request.headers.get('Authorization', '')
    if not h.startswith('Bearer '):
        return None
    token = h[7:].strip()
    cur = db().cursor()
    cur.execute('SELECT s.user_id, u.username, u.nickname FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=%s', (token,))
    row = cur.fetchone()
    return row

def cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return resp

@app.before_request
def pre():
    if request.method == 'OPTIONS':
        return cors_headers(('', 204))

@app.after_request
def after(resp):
    return cors_headers(resp)

# ---------- 账号 ----------
@app.route('/api/register', methods=['POST'])
def register():
    d = request.get_json(silent=True) or {}
    username = (d.get('username') or '').strip()
    password = d.get('password') or ''
    nickname = (d.get('nickname') or '').strip() or username
    if not (2 <= len(username) <= 32):
        return jsonify({'ok': False, 'msg': '用户名需 2-32 个字符'})
    if not (4 <= len(password) <= 64):
        return jsonify({'ok': False, 'msg': '密码需 4-64 个字符'})
    salt = secrets.token_hex(16)
    cur = db().cursor()
    try:
        cur.execute('INSERT INTO users (username, password_hash, nickname) VALUES (%s,%s,%s)',
                    (username, salt + ':' + hash_pw(password, salt), nickname))
    except pymysql.err.IntegrityError:
        return jsonify({'ok': False, 'msg': '用户名已被占用'})
    uid = cur.lastrowid
    token = make_token()
    cur.execute('INSERT INTO sessions (token, user_id) VALUES (%s,%s)', (token, uid))
    return jsonify({'ok': True, 'token': token, 'username': username, 'nickname': nickname})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    username = (d.get('username') or '').strip()
    password = d.get('password') or ''
    cur = db().cursor()
    cur.execute('SELECT * FROM users WHERE username=%s', (username,))
    row = cur.fetchone()
    if not row:
        return jsonify({'ok': False, 'msg': '用户不存在'})
    salt, h = (row['password_hash'] or '').split(':', 1)
    if hash_pw(password, salt) != h:
        return jsonify({'ok': False, 'msg': '密码错误'})
    token = make_token()
    cur.execute('INSERT INTO sessions (token, user_id) VALUES (%s,%s)', (token, row['id']))
    return jsonify({'ok': True, 'token': token, 'username': row['username'], 'nickname': row['nickname']})

@app.route('/api/logout', methods=['POST'])
def logout():
    h = request.headers.get('Authorization', '')
    if h.startswith('Bearer '):
        cur = db().cursor()
        cur.execute('DELETE FROM sessions WHERE token=%s', (h[7:].strip(),))
    return jsonify({'ok': True})

@app.route('/api/me', methods=['GET'])
def me():
    u = auth_user()
    if not u:
        return jsonify({'ok': False, 'msg': '未登录'})
    cur = db().cursor()
    cur.execute('SELECT game, MAX(score) AS best, MAX(played_at) AS last FROM scores WHERE user_id=%s GROUP BY game ORDER BY game', (u['user_id'],))
    rows = cur.fetchall()
    return jsonify({'ok': True, 'username': u['username'], 'nickname': u['nickname'], 'scores': rows})

# ---------- 成绩 ----------
@app.route('/api/score', methods=['POST'])
def upload_score():
    u = auth_user()
    if not u:
        return jsonify({'ok': False, 'msg': '未登录'})
    d = request.get_json(silent=True) or {}
    game = (d.get('game') or '').strip()[:32]
    try:
        score = int(d.get('score', 0))
    except (TypeError, ValueError):
        score = 0
    meta = (d.get('meta') or '')[:255]
    if not game:
        return jsonify({'ok': False, 'msg': '缺少游戏名'})
    cur = db().cursor()
    cur.execute('INSERT INTO scores (user_id, game, score, meta) VALUES (%s,%s,%s,%s)',
                (u['user_id'], game, score, meta))
    return jsonify({'ok': True})

@app.route('/api/scores-batch', methods=['POST'])
def upload_batch():
    u = auth_user()
    if not u:
        return jsonify({'ok': False, 'msg': '未登录'})
    d = request.get_json(silent=True) or {}
    items = d.get('items') or []
    if not isinstance(items, list) or not items:
        return jsonify({'ok': True, 'n': 0})
    cur = db().cursor()
    n = 0
    for it in items:
        game = (it.get('game') or '').strip()[:32]
        try:
            score = int(it.get('score', 0))
        except (TypeError, ValueError):
            continue
        if not game or score <= 0:
            continue
        cur.execute('INSERT INTO scores (user_id, game, score, meta) VALUES (%s,%s,%s,%s)',
                    (u['user_id'], game, score, ''))
        n += 1
    return jsonify({'ok': True, 'n': n})

# 用时/步数越小越好的游戏（排行榜取 MIN，升序）
LOW_BEST_GAMES = {
    'minesweeper', 'sudoku', 'hrd', 'sokoban', 'p15', 'memory', 'lianliankan',
    'nonogram', 'slitherlink', 'hashi', 'nurikabe', 'akari', 'calc24', 'guessnum',
    'checkers', 'shogi', 'draughts', 'wordcard'
}

@app.route('/api/leaderboard/<game>', methods=['GET'])
def leaderboard(game):
    limit = min(int(request.args.get('limit', 20)), 100)
    low = game in LOW_BEST_GAMES
    cur = db().cursor()
    if low:
        cur.execute('''SELECT u.username, u.nickname, MIN(s.score) AS best, MAX(s.meta) AS meta
                       FROM scores s JOIN users u ON u.id=s.user_id
                       WHERE s.game=%s GROUP BY u.id ORDER BY best ASC LIMIT %s''', (game, limit))
    else:
        cur.execute('''SELECT u.username, u.nickname, MAX(s.score) AS best, MAX(s.meta) AS meta
                       FROM scores s JOIN users u ON u.id=s.user_id
                       WHERE s.game=%s GROUP BY u.id ORDER BY best DESC LIMIT %s''', (game, limit))
    rows = cur.fetchall()
    return jsonify({'ok': True, 'game': game, 'low': low, 'rows': rows})

@app.route('/api/games', methods=['GET'])
def games():
    cur = db().cursor()
    cur.execute('SELECT game, COUNT(DISTINCT user_id) AS players, MAX(score) AS top FROM scores GROUP BY game ORDER BY game')
    rows = cur.fetchall()
    return jsonify({'ok': True, 'games': rows})

if __name__ == '__main__':
    port = int(CFG.get('port', 5000))
    app.run(host='127.0.0.1', port=port, threaded=True)
