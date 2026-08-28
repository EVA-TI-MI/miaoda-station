#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_data.py v2.0 - 将爬取的 TXT 小说转换为笔趣阁网页可用的数据文件

功能：
  1. 扫描目录下的所有 .txt 小说文件
  2. 自动读取爬虫生成的 .meta.json 元数据（简介、分类、标签）
  3. 解析书名、作者、章节列表和正文
  4. 规范化章节标题（第001回 → 第一回）
  5. 生成 novels_data.js（网页通过 <script> 标签加载）

用法：
  python build_data.py                    # 默认读取 novels/ 目录
  python build_data.py -i D:\books        # 指定输入目录
  python build_data.py -o D:\tanlan       # 指定输出目录
  python build_data.py --demo             # 生成演示数据（不依赖爬虫）
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ============================================================
#  章节标题正则
# ============================================================

CHAPTER_PATTERNS = [
    r'^第[0-9零一二三四五六七八九十百千万]+[章回节卷集篇]\s*.*$',
    r'^Chapter\s+\d+.*$',
    r'^卷[0-9零一二三四五六七八九十]+[\s:：].*$',
    r'^\d+[\.、]\s*.*$',
    r'^【.+】$',
    r'^〖.+〗$',
]
CHAPTER_RE = re.compile('|'.join(CHAPTER_PATTERNS), re.IGNORECASE)

# ============================================================
#  分类配置（与 biquge.html 一致）
# ============================================================

CATEGORY_COLORS = {
    'xuanhuan': ['#8B0000', '#DC143C', '#FF6347'],
    'xianxia':  ['#191970', '#4169E1', '#87CEEB'],
    'dushi':    ['#2F4F4F', '#5F9EA0', '#B0C4DE'],
    'lishi':    ['#8B4513', '#CD853F', '#DEB887'],
    'kehuan':   ['#000033', '#000080', '#483D8B'],
    'xuanyi':   ['#1C1C1C', '#4A4A4A', '#696969'],
    'youxi':    ['#4B0082', '#8A2BE2', '#DDA0DD'],
    'jingji':   ['#FF4500', '#FF6347', '#FFA07A'],
    'gudian':   ['#5C3317', '#8B4513', '#D2B48C'],
    'mingzhu':  ['#2F4F4F', '#556B2F', '#9ACD32'],
}

CATEGORY_NAMES = {
    'xuanhuan': '玄幻', 'xianxia': '仙侠', 'dushi': '都市',
    'lishi': '历史', 'kehuan': '科幻', 'xuanyi': '悬疑',
    'youxi': '游戏', 'jingji': '竞技', 'gudian': '古典', 'mingzhu': '名著',
}

CATEGORY_MAP = {
    '玄幻': 'xuanhuan', '仙侠': 'xianxia', '修真': 'xianxia', '武侠': 'xianxia',
    '都市': 'dushi', '职场': 'dushi', '言情': 'dushi',
    '历史': 'lishi', '军事': 'lishi', '穿越': 'lishi',
    '科幻': 'kehuan', '末世': 'kehuan',
    '悬疑': 'xuanyi', '推理': 'xuanyi', '恐怖': 'xuanyi',
    '游戏': 'youxi', '竞技': 'jingji', '体育': 'jingji',
    '古典': 'gudian', '名著': 'mingzhu', '公版': 'mingzhu',
}

# 经典公版书评分（基于公认文学地位）
CLASSIC_RATINGS = {
    '三国演义': 9.5, '水浒传': 9.3, '西游记': 9.4, '红楼梦': 9.6,
    '聊斋志异': 9.0, '儒林外史': 8.8, '封神演义': 8.5,
    '金瓶梅': 8.7, '东周列国志': 8.6, '镜花缘': 8.2,
}


# ============================================================
#  数字转中文（用于章节标题规范化）
# ============================================================

_CN_DIGITS = '零一二三四五六七八九'
_CN_UNITS = ['', '十', '百', '千']


def num_to_cn(n: int) -> str:
    """将阿拉伯数字转为中文数字（支持 0-9999）"""
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return '十' + ('' if n % 10 == 0 else _CN_DIGITS[n % 10])
    if n < 100:
        t, o = divmod(n, 10)
        return _CN_DIGITS[t] + '十' + ('' if o == 0 else _CN_DIGITS[o])
    if n < 1000:
        h, rem = divmod(n, 100)
        t, o = divmod(rem, 10)
        r = _CN_DIGITS[h] + '百'
        if t == 0 and o == 0:
            return r
        if t == 0:
            return r + '零' + _CN_DIGITS[o]
        r += _CN_DIGITS[t] + '十'
        if o != 0:
            r += _CN_DIGITS[o]
        return r
    if n < 10000:
        th, rem = divmod(n, 1000)
        rest = num_to_cn(rem) if rem > 0 else ''
        return _CN_DIGITS[th] + '千' + ('' if rem == 0 else ('零' if rem < 100 else '') + rest)
    return str(n)


def normalize_chapter_title(title: str) -> str:
    """
    规范化章节标题：
    "第001回 宴桃园..." → "第一回 宴桃园..."
    "第012章 标题" → "第十二章 标题"
    """
    m = re.match(r'^(第)(0*)(\d+)([回章节卷集篇])(.*)$', title)
    if m:
        prefix, zeros, num_str, unit, rest = m.groups()
        num = int(num_str)
        return f'{prefix}{num_to_cn(num)}{unit}{rest}'
    return title


# ============================================================
#  TXT 解析
# ============================================================

def load_meta(txt_path: Path) -> dict:
    """读取爬虫生成的 .meta.json 元数据"""
    meta_path = txt_path.with_suffix('.meta.json')
    if meta_path.exists():
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def parse_txt(filepath: Path) -> dict:
    """解析单个 TXT 小说文件"""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    # 优先读取爬虫生成的元数据
    meta = load_meta(filepath)

    lines = text.split('\n')

    # 提取书名、作者、简介（文件头部）
    title = meta.get('title', filepath.stem)
    author = meta.get('author', '未知')
    description = meta.get('description', '')
    content_start = 0
    title_found = bool(meta.get('title'))
    author_found = bool(meta.get('author'))

    for i, line in enumerate(lines[:30]):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped.startswith('==='):
            content_start = i + 1
            break
        # 作者行
        if not author_found and '作者' in line_stripped and ('：' in line_stripped or ':' in line_stripped):
            author = re.split(r'[：:]', line_stripped, maxsplit=1)[-1].strip()
            author_found = True
            content_start = i + 1
            continue
        # 简介行
        if '简介' in line_stripped and ('：' in line_stripped or ':' in line_stripped):
            desc_text = re.split(r'[：:]', line_stripped, maxsplit=1)[-1].strip()
            if desc_text and not description:
                description = desc_text
            content_start = i + 1
            continue
        # 第一行非空通常是书名
        if not title_found and i == 0 and len(line_stripped) < 30:
            if not line_stripped.startswith('=') and '下载完成' not in line_stripped:
                title = line_stripped
                title_found = True
                content_start = i + 1
                continue

    # 解析章节
    chapters = []
    current_title = None
    current_lines = []

    def save_chapter():
        if current_title and current_lines:
            body = '\n'.join(current_lines).strip()
            body = re.sub(r'\n=+\n.*$', '', body, flags=re.DOTALL)
            body = re.sub(r'下载完成.*$', '', body, flags=re.DOTALL)
            body = body.strip()
            if body:
                chapters.append({'title': current_title, 'content': body})

    for line in lines[content_start:]:
        stripped = line.strip()
        if not stripped:
            if current_title:
                current_lines.append('')
            continue
        if stripped.startswith('===') or '下载完成' in stripped:
            continue
        if CHAPTER_RE.match(stripped) and len(stripped) < 50:
            save_chapter()
            current_title = stripped
            current_lines = []
        else:
            if current_title:
                current_lines.append(stripped)

    save_chapter()

    # 如果没识别到章节，把全文作为单章
    if not chapters:
        body = '\n'.join(lines[content_start:]).strip()
        body = re.sub(r'\n=+\n.*$', '', body, flags=re.DOTALL)
        if body:
            chapters.append({'title': '正文', 'content': body})

    # 规范化章节标题
    for ch in chapters:
        ch['title'] = normalize_chapter_title(ch['title'])

    # 计算字数（按非空白字符计）
    total_chars = sum(len(re.sub(r'\s', '', c['content'])) for c in chapters)
    words_wan = max(0.1, round(total_chars / 10000, 1))

    # 如果没有简介，用第一章前150字作为摘要
    if not description and chapters:
        first = chapters[0]['content'].replace('\n', '')
        description = first[:150] + ('...' if len(first) > 150 else '')

    return {
        'title': title,
        'author': author,
        'chapters': chapters,
        'words': words_wan,
        'desc': description,
        'category': meta.get('category', ''),
        'tags': meta.get('tags', []),
    }


# ============================================================
#  数据构建
# ============================================================

def guess_category(title: str, desc: str) -> str:
    text = title + desc
    for keyword, cat in CATEGORY_MAP.items():
        if keyword in text:
            return cat
    return 'gudian'


def convert_to_js(novels: list, output_path: Path):
    """将小说列表转换为 novels_data.js"""
    books = []
    for i, novel in enumerate(novels):
        cat = novel.get('category') or guess_category(novel['title'], novel['desc'])
        colors = CATEGORY_COLORS.get(cat, CATEGORY_COLORS['gudian'])
        chapter_count = len(novel['chapters'])

        # 章节内容按空行分段
        chapter_data = []
        for ch in novel['chapters']:
            # 按双换行分段，单换行在同一段内
            raw_paragraphs = re.split(r'\n\s*\n', ch['content'])
            paragraphs = []
            for p in raw_paragraphs:
                p = p.strip().replace('\n', '')
                if p and len(p) > 1:
                    paragraphs.append(p)
            if not paragraphs:
                # 回退：按单换行分割
                paragraphs = [p.strip() for p in ch['content'].split('\n') if p.strip()]
            chapter_data.append({
                'title': ch['title'],
                'paragraphs': paragraphs,
            })

        # 标签：优先使用元数据中的标签，补充分类名
        tags = list(novel.get('tags', []))
        cat_name = CATEGORY_NAMES.get(cat, '其他')
        if cat_name not in tags:
            tags.insert(0, cat_name)
        tags.append('公版书')
        # 去重保持顺序
        seen_tags = set()
        unique_tags = []
        for t in tags:
            if t not in seen_tags:
                seen_tags.add(t)
                unique_tags.append(t)

        # 评分：经典名著使用公认评分
        rating = CLASSIC_RATINGS.get(novel['title'], round(8.5 + (i % 5) * 0.1, 1))

        # 人气：经典名著给较高基础值
        hot = 800000 + i * 50000 if novel['title'] in CLASSIC_RATINGS else 500000 + i * 123456

        book = {
            'id': 100 + i,
            'title': novel['title'],
            'author': novel['author'],
            'category': cat,
            'tags': unique_tags,
            'status': '完结',
            'words': novel['words'],
            'chapters': chapter_count,
            'rating': rating,
            'hot': hot,
            'desc': novel['desc'] or f"{novel['title']}，作者{novel['author']}，共{chapter_count}章。",
            'gradient': colors,
            'source': 'crawler',
            'realContent': chapter_data,
        }
        books.append(book)

    js_lines = [
        '// novels_data.js - 由 build_data.py 自动生成',
        '// 包含爬取的真实小说内容，供 biquge.html 加载',
        'window.NOVELS_DATA = ' + json.dumps(books, ensure_ascii=False, indent=2) + ';',
        '',
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(js_lines))

    return books


# ============================================================
#  演示数据
# ============================================================

def build_demo_data(output_path: Path):
    """生成演示数据（不需要爬虫，用于测试网页集成）"""
    demo_novels = [
        {
            'title': '三国演义',
            'author': '罗贯中',
            'words': 64.0,
            'desc': '滚滚长江东逝水，浪花淘尽英雄。东汉末年，群雄并起，魏蜀吴三分天下，演绎了一段波澜壮阔的历史传奇。',
            'chapters': [
                {'title': '第一回 宴桃园豪杰三结义 斩黄巾英雄首立功', 'paragraphs': [
                    '话说天下大势，分久必合，合久必分。周末七国分争，并入于秦。及秦灭之后，楚、汉分争，又并入于汉。汉朝自高祖斩白蛇而起义，一统天下，后来光武中兴，传至献帝，遂分为三国。',
                    '推其致乱之由，殆始于桓、灵二帝。桓帝禁锢善类，崇信宦官。及桓帝崩，灵帝即位，大将军窦武、太傅陈蕃共相辅佐。时有宦官曹节等弄权，窦武、陈蕃谋诛之，机事不密，反为所害，中涓自此愈横。',
                ]},
                {'title': '第二回 张翼德怒鞭督邮 何国舅谋诛宦竖', 'paragraphs': [
                    '且说董卓字仲颖，陇西临洮人也，官拜河东太守，自来骄傲。当日怠慢了玄德，张飞性发，便欲杀之。玄德与关公急止之曰："他是朝廷命官，岂可擅杀？"',
                ]},
            ],
        },
        {
            'title': '聊斋志异·聂小倩',
            'author': '蒲松龄',
            'words': 3.2,
            'desc': '宁采臣夜宿兰若寺，遇女鬼聂小倩，演绎一段人鬼之间的凄美故事。',
            'chapters': [
                {'title': '聂小倩', 'paragraphs': [
                    '宁采臣，浙人。性慷爽，廉隅自重。每对人言："生平无二色。"适赴金华，至北郭，解装兰若。寺中殿塔壮丽，然蓬蒿没人，似绝行踪。',
                ]},
            ],
        },
    ]

    books = []
    for i, novel in enumerate(demo_novels):
        colors = list(CATEGORY_COLORS.values())[i % len(CATEGORY_COLORS)]
        books.append({
            'id': 100 + i,
            'title': novel['title'],
            'author': novel['author'],
            'category': 'gudian',
            'tags': ['古典', '公版书', '名著'],
            'status': '完结',
            'words': novel['words'],
            'chapters': len(novel['chapters']),
            'rating': 9.5 - i * 0.3,
            'hot': 1000000 - i * 200000,
            'desc': novel['desc'],
            'gradient': colors,
            'source': 'demo',
            'realContent': novel['chapters'],
        })

    js_lines = [
        '// novels_data.js - 演示数据（公版名著节选）',
        'window.NOVELS_DATA = ' + json.dumps(books, ensure_ascii=False, indent=2) + ';',
        '',
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(js_lines))
    return books


# ============================================================
#  命令行接口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='将爬取的TXT小说转换为网页数据文件 v2.0')
    parser.add_argument('-i', '--input', default='novels', help='TXT文件所在目录 (默认: novels)')
    parser.add_argument('-o', '--output', default='.', help='novels_data.js 输出目录 (默认: 当前目录)')
    parser.add_argument('--demo', action='store_true', help='生成演示数据（公版名著节选，不需要爬虫）')
    args = parser.parse_args()

    if args.demo:
        output_path = Path(args.output) / 'novels_data.js'
        books = build_demo_data(output_path)
        print(f'[+] 演示数据已生成: {output_path}')
        for b in books:
            print(f'    - {b["title"]} / {b["author"]} / {b["chapters"]}章 / {b["words"]}万字')
        return

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f'[!] 输入目录不存在: {input_dir}')
        print(f'    请先运行爬虫下载小说，或使用 --demo 生成演示数据')
        sys.exit(1)

    txt_files = sorted(input_dir.glob('*.txt'))
    if not txt_files:
        print(f'[!] 在 {input_dir} 中未找到 TXT 文件')
        sys.exit(1)

    print(f'[*] 发现 {len(txt_files)} 个 TXT 文件')
    novels = []
    for f in txt_files:
        print(f'[*] 解析: {f.name}')
        novel = parse_txt(f)
        print(f'    书名: {novel["title"]}')
        print(f'    作者: {novel["author"]}')
        print(f'    章节: {len(novel["chapters"])} 章')
        print(f'    字数: {novel["words"]} 万')
        if novel['desc']:
            print(f'    简介: {novel["desc"][:60]}...')
        novels.append(novel)

    output_path = Path(args.output) / 'novels_data.js'
    books = convert_to_js(novels, output_path)
    print(f'\n[+] 数据文件已生成: {output_path}')
    for b in books:
        print(f'    - {b["title"]} / {b["author"]} / {b["chapters"]}章 / {b["words"]}万字 / 评分{b["rating"]}')
    print(f'[+] 共 {len(books)} 本小说，刷新 biquge.html 即可看到真实内容')


if __name__ == '__main__':
    main()
