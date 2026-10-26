# -*- coding: utf-8 -*-
"""用 urllib 直接测后端中文全链路（绕过 PowerShell 控制台编码）"""
import json, urllib.request

BASE = 'http://127.0.0.1:5000'

def post(path, payload, token=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json',
                                          **({'Authorization': 'Bearer ' + token} if token else {})})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode('utf-8'))

def get(path, token=None):
    req = urllib.request.Request(BASE + path, headers={'Authorization': 'Bearer ' + token} if token else {})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode('utf-8'))

r = post('/api/register', {'username': '八号用户', 'password': 'pass1234', 'nickname': '八号'})
print('register:', r.get('ok'), r.get('username'), r.get('nickname'), r.get('msg', ''))
if r.get('ok'):
    tok = r['token']
    print('upload:', post('/api/score', {'game': 'snake', 'score': 12345, 'meta': '胜利'}, tok).get('ok'))
    lb = get('/api/leaderboard/snake')
    print('board:', lb.get('rows'))
    me = get('/api/me', tok)
    print('me:', me.get('scores'))
    print('batch:', post('/api/scores-batch', {'items': [{'game': 'sudoku', 'score': 360}, {'game': 'tetris', 'score': 9999}]}, tok))
