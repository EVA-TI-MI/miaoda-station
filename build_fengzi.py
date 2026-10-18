# -*- coding: utf-8 -*-
"""
将 D:\风姿RPG\assets\text\ 下4部风姿物语TXT切分为章节，
输出为墨渊阁(biquge.html)可识别的外挂数据：
  novels/fengzi/fengzi_index.js          —— 书目元数据 + 章节标题（小，随页面加载）
  novels/fengzi/fengzi_payload_<key>.js  —— 章节正文（大，打开该书时按需加载）
"""
import os, re, json, io, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SRC_DIR = r"D:\风姿RPG\assets\text"
OUT_DIR = r"D:\tanlan\novels\fengzi"
os.makedirs(OUT_DIR, exist_ok=True)

# (文件名, book_id, 书名, 简介, gradient, payload键)
BOOKS = [
    ("风姿物语.txt", 101, "风姿物语",
     "罗森代表作《风姿物语》正传。少年李煜于乱世中崛起，剑爵、石字世家、暹罗、稷下……"
     "群雄逐鹿的大陆上，一段混杂着热血、爆笑与深情的玄幻史诗。",
     ["#3a2a12", "#8b6914", "#d4a84b"], "wuyu"),
    ("风姿正传.txt", 102, "风姿正传",
     "《风姿物语》正传主线：恶名一刀、天地有雪、歃血为盟……从杂牌兵团到一代剑爵，"
     "完整收录正传篇章。",
     ["#1a2a3a", "#274b6d", "#6ea8fe"], "zhengzhuan"),
    ("我意天下.txt", 103, "我意天下",
     "罗森·风姿物语系列番外《我意天下》：登基大典、杀神计划、王者之刀，"
     "以更宏大的视角补全风姿世界的帝王篇。",
     ["#3a1a1a", "#6d2727", "#e0794a"], "wiyi"),
    ("外传前传.txt", 104, "风姿物语·外传前传",
     "风姿物语系列外传与前传合集：西湖畔相识、千里姻缘、人间相思……"
     "正文之外的情爱与因果，补全众生群像。",
     ["#2a1a3a", "#5b3a8c", "#b07fe0"], "waizhuan"),
]

# 章节标题行：行首“第X章/回/节/卷/部”，整行结束（允许最长约48字标题）
HEAD_RE = re.compile(r"^\s*(第[0-9一二三四五六七八九十百千零两]+[章回节卷部][^\n]{0,48})\s*$", re.M)
# 标题尾部的页码残留：如 “第一章 恶名一刀2” -> “第一章 恶名一刀”
TRAIL_DIGITS = re.compile(r"[0-9０-９\s]+$")
# 纯页码行
PURE_PAGE = re.compile(r"^\s*[0-9]{1,4}\s*$")


def clean_title(raw: str) -> str:
    t = raw.strip()
    t = TRAIL_DIGITS.sub("", t).strip()
    return t


# 目录行特征：标题尾部带页码数字（如 “第一章 恶名一刀2”）
TRAIL_PAGE = re.compile(r"[0-9０-９]\s*$")

def split_chapters(text: str):
    """返回 [(title, content_text), ...]。
    文件开头为作者简介 + 目录页；目录里的章节标题行尾都带页码数字，
    正文的章节标题行尾干净。以“第一个无尾页数字的章节行”作为正文起点。"""
    lines = text.split("\n")
    body_start = 0
    for i, ln in enumerate(lines):
        if HEAD_RE.match(ln) and not TRAIL_PAGE.search(ln.strip()):
            body_start = i
            break
    lines = lines[body_start:]

    chapters = []
    cur_title = None
    buf = []
    for ln in lines:
        m = HEAD_RE.match(ln)
        if m:
            if cur_title is not None:
                chapters.append((cur_title, "\n".join(buf)))
            cur_title = clean_title(m.group(1))
            buf = []
        else:
            buf.append(ln)
    if cur_title is not None:
        chapters.append((cur_title, "\n".join(buf)))
    return chapters


def to_paragraphs(content: str):
    paras = []
    for ln in content.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if PURE_PAGE.match(s):
            continue
        if len(s) < 2:
            continue
        paras.append(s)
    return paras


index_books = []
summary = []

for fname, bid, title, desc, gradient, key in BOOKS:
    path = os.path.join(SRC_DIR, fname)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    chapters = split_chapters(text)
    total_chars = 0
    payload = []
    for ct, ctext in chapters:
        paras = to_paragraphs(ctext)
        if not paras:
            continue
        plen = sum(len(p) for p in paras)
        total_chars += plen
        payload.append({"title": ct, "paragraphs": paras})

    n = len(payload)
    words_wan = round(total_chars / 10000, 1)

    # 元数据条目：realContent 只保留标题，正文置 None，正文走 lazyFile
    meta = {
        "id": bid,
        "title": title,
        "author": "罗森",
        "category": "xuanhuan",
        "tags": ["玄幻", "风姿物语", "罗森", "公版全文"],
        "status": "完结",
        "words": words_wan,
        "chapters": n,
        "rating": 9.0,
        "hot": 300000 + bid * 7777,
        "desc": desc,
        "gradient": gradient,
        "source": "crawler",
        "lazyFile": "novels/fengzi/fengzi_payload_%s.js" % key,
        "realContent": [{"title": c["title"], "paragraphs": None} for c in payload],
    }
    index_books.append(meta)

    # 写正文 payload 文件
    payload_js = (
        "// 风姿物语正文数据（按需加载）book_id=%d %s\n"
        "window.FENGZI_PAYLOAD = window.FENGZI_PAYLOAD || {};\n"
        "window.FENGZI_PAYLOAD[%d] = %s;\n"
        % (bid, title, bid, json.dumps(payload, ensure_ascii=False))
    )
    ppath = os.path.join(OUT_DIR, "fengzi_payload_%s.js" % key)
    with open(ppath, "w", encoding="utf-8") as f:
        f.write(payload_js)

    summary.append((title, bid, n, words_wan, os.path.getsize(ppath)))

# 写 index 文件
index_js = (
    "// fengzi_index.js —— 风姿物语系列书目元数据（章节标题列表），正文见 FENGZI_PAYLOAD\n"
    "window.FENGZI_BOOKS = window.FENGZI_BOOKS || %s;\n"
    % json.dumps(index_books, ensure_ascii=False, indent=2)
)
ipath = os.path.join(OUT_DIR, "fengzi_index.js")
with open(ipath, "w", encoding="utf-8") as f:
    f.write(index_js)

print("== 构建完成 ==")
for title, bid, n, w, sz in summary:
    print("  %-18s id=%d  章节=%4d  字数=%.1f万  payload=%d KB" % (title, bid, n, w, sz//1024))
print("index:", ipath, os.path.getsize(ipath)//1024, "KB")
