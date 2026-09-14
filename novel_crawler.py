#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说爬虫 (Novel Crawler) v3.0
==============================
一个用于学习目的的多站点小说下载工具。

功能：
  - 多站点适配（笔趣阁模板 / 国学荟萃 / 通用自动识别），支持自动检测
  - 异步并发下载（aiohttp），可控制并发数和延时
  - 断点续传 / 增量更新（跳过已下载章节，只补新章）
  - 自动重试（指数退避）+ 终轮失败补抓 + 失败章节清单
  - 智能编码检测（meta/BOM/chardet，自动兼容 UTF-8 与 GBK/GB18030）
  - 章节分页自动合并（如 123.html / 123_2.html 自动拼接）
  - 内置文本清洗（广告过滤、错字修正钩子）
  - 导出 TXT / EPUB（电子书，可用阅读器打开）+ meta.json 元数据
  - 关键词搜索（需指定站点搜索入口 --search-site）
  - 批量下载（-l 清单文件，一行一个目录页 URL）
  - 自定义代理 / UA / Referer / Cookie
  - 可选一键流程：爬取 → 文本修正 → 生成网页数据
  - 实时进度条显示

法律声明：
  本工具仅供学习编程和网络技术使用。使用时请遵守：
  1. 仅下载你有权访问的内容（公版书、作者授权作品等）
  2. 遵守目标网站的 robots.txt 和服务条款
  3. 合理控制请求频率，勿对目标服务器造成压力
  4. 下载内容请勿用于商业用途或非法传播
  使用者自行承担因不当使用产生的一切法律责任。
"""

import argparse
import asyncio
import html as html_lib
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


# ============================================================
#  数据模型
# ============================================================

@dataclass
class Chapter:
    """单个章节"""
    index: int
    title: str
    url: str
    content: str = ""
    status: str = "pending"  # pending / done / error


@dataclass
class Novel:
    """一本小说的元信息"""
    title: str
    author: str
    url: str
    chapters: list = field(default_factory=list)
    output_dir: str = "novels"
    description: str = ""
    category: str = "gudian"
    tags: list = field(default_factory=list)


# ============================================================
#  站点适配器
# ============================================================

class SiteAdapter:
    """站点适配器基类"""

    name = "base"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def match(self, url: str) -> bool:
        return False

    def parse_index(self, html: str, base_url: str) -> dict:
        raise NotImplementedError

    def parse_chapter(self, html: str) -> tuple:
        raise NotImplementedError

    def clean_text(self, text: str) -> str:
        """站点通用的文本清洗（广告过滤等），子类可覆盖"""
        ad_patterns = [
            r"笔趣阁.*?最新章节[。！!]?",
            r"手机用户请浏览.*",
            r"本章未完.*?点击下一页继续阅读",
            r"百度搜索.*",
            r"请记住本书首发域名.*",
            r"https?://\S+",
            r"www\.\S+\.(com|net|org|cn)",
        ]
        for pat in ad_patterns:
            text = re.sub(pat, "", text)
        return text.strip()

    def next_page_url(self, html_text: str, current_url: str):
        """识别章节内分页（如 123.html -> 123_2.html），返回绝对 URL；无则 None。
        只认可“同一章节序号 + _N 后缀”的链接，避免把下一章误当分页拼接。"""
        if BeautifulSoup is None:
            return None
        soup = BeautifulSoup(html_text, "html.parser")
        stem = re.sub(r'(_\d+)?\.s?html?$', '', urlparse(current_url).path, flags=re.IGNORECASE)
        for a in soup.find_all("a", href=True):
            t = a.get_text(strip=True).replace(" ", "")
            if not t or not (t in ("下一页", "下页", "next", "Next", "››", "»") or t.startswith("下一页")):
                continue
            href = a["href"].strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript"):
                continue
            nxt = urljoin(current_url, href)
            npath = urlparse(nxt).path
            if nxt != current_url and npath.startswith(stem) and re.search(r'_\d+\.s?html?$', npath, re.IGNORECASE):
                return nxt
        return None


# ============================================================
#  编码检测
# ============================================================

def detect_html_encoding(raw: bytes) -> str:
    """按 BOM、meta charset、chardet、UTF-8 试解的顺序判断网页编码，GB 系列统一到 GB18030。"""
    if not raw:
        return "utf-8"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    head = raw[:4096].decode("ascii", "ignore").lower()
    m = re.search(r'charset=["\']?\s*([a-z0-9_\-]+)', head)
    enc = None
    if m and m.group(1) not in ("", "unicode"):
        enc = m.group(1)
    if not enc:
        try:
            import chardet  # 可选依赖
            r = chardet.detect(raw)
            if r and r.get("encoding"):
                enc = r["encoding"]
        except Exception:
            enc = None
    if enc:
        return {"gb2312": "gb18030", "gbk": "gb18030"}.get(enc.lower(), enc)
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gb18030"


def decode_html(raw: bytes, forced: str = None) -> str:
    return raw.decode(forced or detect_html_encoding(raw), errors="replace")


class GuoxueHuicuiAdapter(SiteAdapter):
    """
    国学荟萃网适配器 (guoxuehuicui.com)

    站点结构：
      - 目录页：章节链接直接在页面中，文本格式为"第XXX回 标题"
      - 书籍信息：h1 书名，作者在 title 标签或 people-info 中
      - 章节页：标题在 <h1>，正文在 <div class="main-content gushi-info"> 的 <p> 中，
                段落以 <br/><br/> 分隔，含内联 <a> 标签需清除
    """

    name = "guoxue"

    # 已知公版书的元数据
    KNOWN_BOOKS = {
        "三国演义": {
            "category": "gudian",
            "tags": ["古典名著", "四大名著", "历史演义", "章回小说"],
            "description": (
                "《三国演义》是中国第一部长篇章回体历史演义小说，以描写战争为主，"
                "反映了魏、蜀、吴三个政治集团之间的政治和军事斗争。"
                "全书可大致分为黄巾之乱、董卓之乱、群雄逐鹿、三国鼎立、三国归晋五大部分。"
                "作者罗贯中（约1330年—约1400年），名本，字贯中，号湖海散人，元末明初小说家。"
            ),
        },
        "水浒传": {
            "category": "gudian",
            "tags": ["古典名著", "四大名著", "英雄传奇", "章回小说"],
            "description": (
                "《水浒传》是中国历史上第一部用白话文写成的章回小说，以宋江领导的起义军为主要题材，"
                "通过一系列梁山英雄反抗压迫、英勇斗争的故事，暴露了北宋末年统治阶级的腐朽和残暴。"
            ),
        },
        "西游记": {
            "category": "gudian",
            "tags": ["古典名著", "四大名著", "神魔小说", "章回小说"],
            "description": (
                "《西游记》是中国古代第一部浪漫主义章回体长篇神魔小说，主要描写孙悟空出世及大闹天宫后，"
                "遇见了唐僧、猪八戒、沙僧和白龙马，西行取经，一路上历经艰险、降妖伏魔的故事。"
            ),
        },
        "红楼梦": {
            "category": "gudian",
            "tags": ["古典名著", "四大名著", "世情小说", "章回小说"],
            "description": (
                "《红楼梦》是中国古代章回体长篇小说，中国古典四大名著之一，"
                "小说以贾、史、王、薛四大家族的兴衰为背景，以富贵公子贾宝玉为视角，"
                "描绘了一批举止见识出于须眉之上的闺阁佳人的人生百态。"
            ),
        },
    }

    def match(self, url: str) -> bool:
        return "guoxuehuicui.com" in url

    def parse_index(self, html: str, base_url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        # 书名
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.get_text(strip=True).split("_")[0].split("-")[0].strip()
        if not title:
            title = "未知书名"

        # 作者
        author = "未知"
        for text in soup.stripped_strings:
            if "作者" in text and ("：" in text or ":" in text):
                parts = re.split(r"[：:]", text, maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    author = parts[1].strip()
                    break
        if author == "未知" and soup.title:
            title_text = soup.title.get_text(strip=True)
            m = re.search(r"作者(.+?)[_|]", title_text)
            if m:
                author = m.group(1).strip()
        if author == "未知":
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                m = re.search(r"作者是[^，。]*?的?小说家?(.+?)[，。]", meta_desc["content"])
                if m:
                    author = m.group(1).strip()
        if author == "未知":
            info_div = soup.find("div", class_="people-info")
            if info_div:
                a_tag = info_div.find("a")
                if a_tag:
                    author = a_tag.get_text(strip=True)

        # 简介
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()
        if not description:
            # 尝试从页面 intro/summary 区域提取
            for cls in ["intro", "summary", "book-intro", "desc", "book-dec"]:
                intro_div = soup.find("div", class_=cls)
                if intro_div:
                    description = intro_div.get_text(strip=True)
                    break

        # 使用已知书籍元数据补充
        known = self.KNOWN_BOOKS.get(title, {})
        category = known.get("category", "gudian")
        tags = known.get("tags", ["古典文学", "公版书"])
        if known.get("description"):
            description = known["description"]

        # 章节列表
        chapters = []
        seen_urls = set()
        for a_tag in soup.find_all("a", href=True):
            ch_title = a_tag.get_text(strip=True)
            if re.match(r"^第\d+[回章节卷]", ch_title):
                full_url = urljoin(base_url, a_tag["href"])
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    chapters.append({"title": ch_title, "url": full_url})

        return {
            "title": title,
            "author": author,
            "chapters": chapters,
            "description": description,
            "category": category,
            "tags": tags,
        }

    def parse_chapter(self, html: str) -> tuple:
        soup = BeautifulSoup(html, "html.parser")

        # 标题
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            m = re.search(r"(第\d+[回章节卷].*?)[》」』]?$", title)
            if m:
                title = m.group(1)

        # 正文
        content_div = soup.find("div", class_="main-content")
        if not content_div:
            content_div = soup.find("div", class_="gushi-info")

        paragraphs = []
        if content_div:
            # 只移除脚本/广告标签，不删 div（避免误删内容容器）
            for tag in content_div.find_all(["script", "style", "ins", "iframe"]):
                tag.decompose()

            p_tag = content_div.find("p")
            if p_tag:
                for a in p_tag.find_all("a"):
                    a.replace_with(a.get_text())
                raw_html = str(p_tag)
                raw_parts = re.split(r"<br\s*/?>\s*<br\s*/?>", raw_html, flags=re.IGNORECASE)
                for part in raw_parts:
                    text = BeautifulSoup(part, "html.parser").get_text("", strip=True)
                    text = text.strip("\u3000\r\n\t ")
                    if text and len(text) > 1:
                        paragraphs.append(text)

        content = "\n\n".join(paragraphs)
        return title, content.strip()


class BiqugeAdapter(SiteAdapter):
    """
    笔趣阁类网站适配器

    典型结构：
      - 目录页：<div id="list"> 内的 <dd><a href="...">章节名</a></dd>
      - 书籍信息：<div id="info"> 内的 <h1>书名</h1> 和 <p>作者：xxx</p>
      - 章节页：<div id="content"> 正文，<h1> 标题
    """

    name = "biquge"

    def match(self, url: str) -> bool:
        # 笔趣阁类站点域名特征（可扩展）
        biquge_domains = ["biquge", "biqu", "bqg", "xbiquge", "ibiquge", "biquwx"]
        url_lower = url.lower()
        return any(d in url_lower for d in biquge_domains)

    def parse_index(self, html: str, base_url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        if not title:
            og = soup.find("meta", property="og:title")
            if og:
                title = og.get("content", "")
        if not title:
            title = "未知书名"

        author = "未知"
        info_div = soup.find("div", id="info")
        if info_div:
            for p in info_div.find_all("p"):
                text = p.get_text(strip=True)
                if "作者" in text:
                    author = re.split(r"[：:]", text, maxsplit=1)[-1].strip()
                    break
        if author == "未知":
            og_author = soup.find("meta", property="og:novel:author")
            if og_author:
                author = og_author.get("content", "未知")

        # 简介
        description = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "")
        if not description:
            intro = soup.find("div", id="intro") or soup.find("div", class_="intro")
            if intro:
                description = intro.get_text(strip=True)

        chapters = []
        list_div = soup.find("div", id="list") or soup.find("div", class_="listmain")
        if list_div:
            for a_tag in list_div.find_all("a", href=True):
                href = a_tag["href"]
                ch_title = a_tag.get_text(strip=True)
                if ch_title and href:
                    chapters.append({"title": ch_title, "url": urljoin(base_url, href)})

        seen = set()
        unique = []
        for ch in chapters:
            if ch["url"] not in seen:
                seen.add(ch["url"])
                unique.append(ch)

        return {
            "title": title,
            "author": author,
            "chapters": unique,
            "description": description,
            "category": "xuanhuan",
            "tags": ["网络小说"],
        }

    def parse_chapter(self, html: str) -> tuple:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            h2 = soup.find("h2")
            if h2:
                title = h2.get_text(strip=True)

        content_div = (
            soup.find("div", id="content")
            or soup.find("div", id="chaptercontent")
            or soup.find("div", class_="content")
            or soup.find("article")
        )

        paragraphs = []
        if content_div:
            for tag in content_div.find_all(["script", "style", "ins", "iframe"]):
                tag.decompose()
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            if not paragraphs:
                raw = content_div.get_text("\n", strip=True)
                paragraphs = [line.strip() for line in raw.split("\n") if line.strip()]

        content = "\n\n".join(paragraphs)
        return title, self.clean_text(content)


class GenericAdapter(SiteAdapter):
    """通用适配器：尝试多种常见选择器自动识别目录和正文结构。"""

    name = "generic"

    def match(self, url: str) -> bool:
        return True  # 兜底适配器

    def parse_index(self, html: str, base_url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True).split("_")[0].split("-")[0].strip()
        if not title:  # 回退到 h1 / og:title
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
        if not title:
            og = soup.find("meta", property="og:title")
            if og:
                title = og.get("content", "")
        if not title:
            title = "未知书名"

        author = "未知"
        og_author = soup.find("meta", attrs={"name": "author"})
        if og_author:
            author = og_author.get("content", "未知")
        if author == "未知":  # 回退到 #info 内“作者：”行
            info = soup.find("div", id="info")
            if info:
                for p in info.find_all("p"):
                    txt = p.get_text(strip=True)
                    if "作者" in txt:
                        author = re.split(r"[：:]", txt, maxsplit=1)[-1].strip()
                        break

        description = ""
        og_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc:
            description = og_desc.get("content", "")

        chapters = []
        selectors = [
            ("div", {"id": "list"}),
            ("div", {"class": "catalog"}),
            ("div", {"class": "chapter-list"}),
            ("ul", {"class": "chapter"}),
            ("div", {"id": "catalog"}),
            ("div", {"class": "book-list"}),
        ]
        for tag_name, attrs in selectors:
            container = soup.find(tag_name, attrs)
            if container:
                for a_tag in container.find_all("a", href=True):
                    ch_title = a_tag.get_text(strip=True)
                    if ch_title and len(ch_title) > 1:
                        chapters.append({"title": ch_title, "url": urljoin(base_url, a_tag["href"])})
                if chapters:
                    break

        seen = set()
        unique = []
        for ch in chapters:
            if ch["url"] not in seen:
                seen.add(ch["url"])
                unique.append(ch)

        return {
            "title": title,
            "author": author,
            "chapters": unique,
            "description": description,
            "category": "gudian",
            "tags": ["公版书"],
        }

    def parse_chapter(self, html: str) -> tuple:
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        for tag in ["h1", "h2", "h3"]:
            found = soup.find(tag)
            if found:
                title = found.get_text(strip=True)
                break

        content_div = None
        for selector in [
            ("div", {"id": "content"}),
            ("div", {"id": "chaptercontent"}),
            ("div", {"id": "booktext"}),
            ("div", {"class": "content"}),
            ("div", {"class": "chapter-content"}),
            ("div", {"class": "text"}),
            ("div", {"class": "main-content"}),
            ("article", {}),
        ]:
            content_div = soup.find(selector[0], selector[1])
            if content_div:
                break

        paragraphs = []
        if content_div:
            for tag in content_div.find_all(["script", "style", "ins", "iframe"]):
                tag.decompose()
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            if not paragraphs:
                content = content_div.get_text("\n", strip=True)
                paragraphs = [l.strip() for l in content.split("\n") if l.strip()]

        content = "\n\n".join(paragraphs)
        return title, self.clean_text(content)


# ============================================================
#  适配器注册表
# ============================================================

ADAPTERS = [GuoxueHuicuiAdapter, BiqugeAdapter, GenericAdapter]


def detect_adapter(url: str) -> SiteAdapter:
    """根据 URL 自动检测最合适的适配器"""
    for cls in ADAPTERS:
        adapter = cls()
        if adapter.name != "generic" and adapter.match(url):
            return adapter
    return GenericAdapter()


def get_adapter(name: str, url: str = "") -> SiteAdapter:
    """按名称获取适配器，'auto' 时自动检测"""
    if name == "auto":
        return detect_adapter(url)
    for cls in ADAPTERS:
        if cls.name == name:
            return cls()
    return GenericAdapter()


# ============================================================
#  文本修正（可选，爬取后自动调用）
# ============================================================

def apply_text_fixes(text: str) -> str:
    """
    对爬取的文本应用常见修正。
    这是一个轻量版修正，完整修正请使用 fix_text.py。
    主要处理：广告残留、多余空白、全角空格。
    """
    # 清理广告
    ad_patterns = [
        r"笔趣阁.*?最新章节[。！!]?",
        r"手机用户请浏览.*",
        r"本章未完.*?点击下一页继续阅读",
        r"百度搜索.*",
        r"请记住本书首发域名.*",
        r"https?://\S+",
    ]
    for pat in ad_patterns:
        text = re.sub(pat, "", text)

    # 规范化空白：每行去掉首尾全角/半角空格
    lines = text.split("\n")
    lines = [line.strip("\u3000\r\n\t ") for line in lines]
    # 合并3个以上连续空行为2个
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
#  爬虫核心
# ============================================================

class NovelCrawler:
    """小说爬虫主类"""

    def __init__(
        self,
        adapter: SiteAdapter = None,
        delay: float = 1.0,
        max_concurrent: int = 3,
        timeout: int = 15,
        max_retries: int = 3,
        output_dir: str = "novels",
        encoding: str = None,
        auto_fix: bool = False,
        proxy: str = None,
        user_agent: str = None,
        referer: str = None,
        cookie: str = None,
        export_format: str = "txt",
        merge_pages: bool = True,
    ):
        self.adapter = adapter or GenericAdapter()
        self.delay = delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = aiohttp.ClientTimeout(total=timeout) if aiohttp else None
        self.max_retries = max_retries
        self.output_dir = Path(output_dir)
        self.encoding = encoding
        self.auto_fix = auto_fix
        self.proxy = proxy
        self.export_format = (export_format or "txt").lower()
        self.merge_pages = merge_pages
        # 允许覆盖 UA / 追加 Referer、Cookie
        self.req_headers = dict(self.adapter.headers)
        if user_agent:
            self.req_headers["User-Agent"] = user_agent
        if referer:
            self.req_headers["Referer"] = referer
        if cookie:
            self.req_headers["Cookie"] = cookie
        self.session = None
        self.stats = {"done": 0, "error": 0, "total": 0}
        self._cached_count = 0

    async def _fetch(self, url: str) -> str:
        """带重试和延时的 HTTP GET"""
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.semaphore:
                    kw = dict(headers=self.req_headers, timeout=self.timeout)
                    if self.proxy:
                        kw["proxy"] = self.proxy
                    async with self.session.get(url, **kw) as resp:
                        if resp.status == 200:
                            raw = await resp.read()
                            return decode_html(raw, self.encoding)
                        elif resp.status in (429, 503):
                            wait = self.delay * attempt * 2
                            print(f"  [!] 服务器繁忙 ({resp.status})，等待 {wait:.1f}s 后重试...")
                            await asyncio.sleep(wait)
                        else:
                            print(f"  [!] HTTP {resp.status}: {url}")
                            if attempt < self.max_retries:
                                await asyncio.sleep(self.delay * attempt)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self.max_retries:
                    wait = self.delay * attempt
                    print(f"  [!] 请求失败 ({e.__class__.__name__})，{wait:.1f}s 后重试 ({attempt}/{self.max_retries})")
                    await asyncio.sleep(wait)
                else:
                    raise
        return ""

    async def fetch_index(self, url: str) -> Novel:
        """获取并解析目录页"""
        print(f"[*] 正在获取目录页: {url}")
        html = await self._fetch(url)
        if not html:
            raise RuntimeError("无法获取目录页内容")

        info = self.adapter.parse_index(html, url)
        novel = Novel(
            title=info["title"],
            author=info["author"],
            url=url,
            output_dir=str(self.output_dir),
            description=info.get("description", ""),
            category=info.get("category", "gudian"),
            tags=info.get("tags", []),
        )
        for i, ch in enumerate(info["chapters"]):
            novel.chapters.append(Chapter(index=i, title=ch["title"], url=ch["url"]))

        print(f"[+] 书名: {novel.title}")
        print(f"[+] 作者: {novel.author}")
        print(f"[+] 共发现 {len(novel.chapters)} 个章节")
        return novel

    async def fetch_chapter(self, chapter: Chapter) -> Chapter:
        """获取单个章节内容"""
        async with self.semaphore:
            await asyncio.sleep(self.delay)

        html = await self._fetch(chapter.url)
        if not html:
            chapter.status = "error"
            self.stats["error"] += 1
            return chapter

        title, content = self.adapter.parse_chapter(html)
        chapter.title = title or chapter.title
        parts = [content] if content else []

        # 章节内分页自动合并（123.html -> 123_2.html ...），最多 30 页防死循环
        if self.merge_pages:
            page_url, guard = chapter.url, 0
            while guard < 30:
                nxt = self.adapter.next_page_url(html, page_url)
                if not nxt:
                    break
                guard += 1
                page_url = nxt
                html = await self._fetch(nxt)
                if not html:
                    break
                _, more = self.adapter.parse_chapter(html)
                if more:
                    parts.append(more)

        content = "\n\n".join(p for p in parts if p)
        chapter.content = content

        # 自动文本修正
        if self.auto_fix and content:
            chapter.content = apply_text_fixes(content)

        chapter.status = "done" if chapter.content else "error"
        if chapter.content:
            self.stats["done"] += 1
        else:
            self.stats["error"] += 1
        return chapter

    def _print_progress(self):
        total = self.stats["total"]
        done = self.stats["done"] + self.stats["error"]
        if total == 0:
            return
        pct = done / total
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(
            f"\r  进度: [{bar}] {done}/{total} "
            f"({pct*100:.1f}%)  成功:{self.stats['done']} 失败:{self.stats['error']}"
        )
        sys.stdout.flush()
        if done == total:
            print()

    async def crawl(self, url: str) -> Novel:
        """完整爬取流程"""
        if aiohttp is None:
            raise RuntimeError("缺少 aiohttp 库，请运行: pip install aiohttp beautifulsoup4")

        connector = aiohttp.TCPConnector(limit=self.semaphore._value, force_close=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            self.session = session

            novel = await self.fetch_index(url)
            if not novel.chapters:
                print("[!] 未找到任何章节链接，请检查 URL 是否为目录页，或尝试使用 -a generic")
                return novel

            self.output_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
            cache_dir = self.output_dir / f".{safe_title}_cache"
            cache_dir.mkdir(exist_ok=True)

            # 加载缓存（缓存中已存储修正后的文本）
            pending = []
            for ch in novel.chapters:
                cache_file = cache_dir / f"{ch.index:05d}.txt"
                if cache_file.exists():
                    cached = cache_file.read_text(encoding="utf-8")
                    if cached:
                        ch.content = cached
                        ch.status = "done"
                        self.stats["done"] += 1
                        self._cached_count += 1
                        continue
                pending.append(ch)

            self.stats["total"] = len(novel.chapters)
            skipped = len(novel.chapters) - len(pending)
            if skipped > 0:
                print(f"[*] 断点续传: 已完成 {skipped} 章，剩余 {len(pending)} 章")

            if pending:
                print(f"[*] 开始下载 (并发: {self.semaphore._value}, 延时: {self.delay}s)...")
                tasks = [asyncio.create_task(self._fetch_and_cache(ch, cache_dir)) for ch in pending]
                for coro in asyncio.as_completed(tasks):
                    await coro
                    self._print_progress()

            # 终轮补抓：首轮失败的章节顺序重试一次
            failed_ch = [ch for ch in novel.chapters if ch.status != "done"]
            if failed_ch:
                print(f"[*] 终轮补抓 {len(failed_ch)} 个失败章节...")
                for ch in failed_ch:
                    self.stats["error"] = max(0, self.stats["error"] - 1)
                    await self._fetch_and_cache(ch, cache_dir)
                    if ch.status == "done":
                        self.stats["done"] += 1
                    else:
                        self.stats["error"] += 1

        # 失败章节清单
        failed_idx = [ch.index + 1 for ch in novel.chapters if ch.status != "done"]
        if failed_idx:
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
            fl = self.output_dir / f"{safe_title}.failed.txt"
            fl.write_text("\n".join(map(str, failed_idx)), encoding="utf-8")
            print(f"[!] 仍有 {len(failed_idx)} 章失败，清单已写入: {fl}")

        newly = max(0, self.stats["done"] - self._cached_count)
        print(f"[*] 本次新获取 {newly} 章，沿用缓存 {self._cached_count} 章")
        if self.export_format in ("txt", "both"):
            self._merge_to_txt(novel, cache_dir)
        if self.export_format in ("epub", "both"):
            self._merge_to_epub(novel, cache_dir)
        self._save_meta(novel)
        return novel

    async def _fetch_and_cache(self, chapter: Chapter, cache_dir: Path):
        try:
            await self.fetch_chapter(chapter)
            if chapter.status == "done":
                cache_file = cache_dir / f"{chapter.index:05d}.txt"
                cache_file.write_text(chapter.content, encoding="utf-8")
        except Exception as e:
            chapter.status = "error"
            self.stats["error"] += 1
            print(f"\n  [!] 第{chapter.index + 1}章下载失败: {e}")

    def _merge_to_txt(self, novel: Novel, cache_dir: Path):
        """将所有章节合并为 TXT"""
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
        output_file = self.output_dir / f"{safe_title}.txt"

        print(f"[*] 正在合并到: {output_file}")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"{novel.title}\n")
            f.write(f"作者：{novel.author}\n")
            if novel.description:
                f.write(f"简介：{novel.description}\n")
            f.write("=" * 50 + "\n\n")

            success = 0
            failed = []
            for ch in novel.chapters:
                if not ch.content:
                    cache_file = cache_dir / f"{ch.index:05d}.txt"
                    if cache_file.exists():
                        ch.content = cache_file.read_text(encoding="utf-8")
                        ch.status = "done"

                if ch.content:
                    f.write(f"\n{ch.title}\n\n")
                    f.write(ch.content)
                    f.write("\n")
                    success += 1
                else:
                    f.write(f"\n{ch.title}\n\n[本章下载失败]\n")
                    failed.append(ch.index + 1)

            f.write("\n" + "=" * 50 + "\n")
            f.write(f"下载完成: 共 {len(novel.chapters)} 章，成功 {success} 章")
            if failed:
                f.write(f"，失败 {len(failed)} 章 (章节号: {', '.join(map(str, failed[:20]))})")
            f.write("\n")

        print(f"[+] 已保存: {output_file}")
        print(f"[+] 成功 {success}/{len(novel.chapters)} 章", end="")
        if failed:
            print(f"，失败 {len(failed)} 章（可重新运行命令续传）")
        else:
            print(" ✓ 全部成功")

    def _save_meta(self, novel: Novel):
        """保存元数据为 meta.json，供 build_data.py 使用"""
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
        meta_file = self.output_dir / f"{safe_title}.meta.json"
        meta = {
            "title": novel.title,
            "author": novel.author,
            "description": novel.description,
            "category": novel.category,
            "tags": novel.tags,
            "chapters": len(novel.chapters),
            "source_url": novel.url,
            "adapter": self.adapter.name,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"[+] 元数据已保存: {meta_file}")

    def _iter_saved_chapters(self, novel: Novel, cache_dir: Path):
        """统一从内存/缓存读取章节正文，返回 (chapter, 正文) 列表。"""
        out = []
        for ch in novel.chapters:
            content = ch.content
            if not content:
                cf = cache_dir / f"{ch.index:05d}.txt"
                if cf.exists():
                    content = cf.read_text(encoding="utf-8")
            out.append((ch, content or ""))
        return out

    def _merge_to_epub(self, novel: Novel, cache_dir: Path):
        """导出为标准 EPUB2 电子书（仅用标准库 zipfile，无需第三方依赖）。"""
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
        epub_path = self.output_dir / f"{safe_title}.epub"
        print(f"[*] 正在生成 EPUB: {epub_path}")
        esc = lambda t: html_lib.escape(t or "", quote=True)

        def xhtml_doc(title, paras):
            body = "\n".join(f"<p>{esc(p)}</p>" for p in paras.split("\n") if p.strip())
            return (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
                f"<title>{esc(title)}</title></head><body>\n"
                f"<h2>{esc(title)}</h2>\n{body}\n</body></html>"
            )

        chapters = self._iter_saved_chapters(novel, cache_dir)
        manifest, spine, ncx_items, files = [], [], [], []
        # 封面/书名页
        cover = xhtml_doc(novel.title, f"作者：{novel.author}\n\n{novel.description}".strip())
        files.append(("OEBPS/Text/cover.xhtml", cover))
        manifest.append(('<item id="cover" href="Text/cover.xhtml" media-type="application/xhtml+xml"/>'))
        spine.append('<itemref idref="cover"/>')
        for i, (ch, content) in enumerate(chapters, start=1):
            cid = f"ch{i:05d}"
            href = f"Text/{cid}.xhtml"
            files.append((f"OEBPS/{href}", xhtml_doc(ch.title, content)))
            manifest.append(f'<item id="{cid}" href="{href}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{cid}"/>')
            ncx_items.append(
                f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{esc(ch.title)}</text></navLabel>'
                f'<content src="{href}"/></navPoint>'
            )

        uid = "urn:uuid:" + re.sub(r"[^a-f0-9]", "", f"{novel.title}{novel.author}".encode("utf-8").hex())[:32].zfill(32)
        content_opf = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">\n'
            f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'<dc:identifier id="bookid">{uid}</dc:identifier>\n'
            f'<dc:title>{esc(novel.title)}</dc:title>\n'
            f'<dc:creator>{esc(novel.author)}</dc:creator>\n'
            '<dc:language>zh-CN</dc:language>\n</metadata>\n'
            '<manifest>\n' + "\n".join(manifest) +
            '\n<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n</manifest>\n'
            '<spine toc="ncx">\n' + "\n".join(spine) + "\n</spine>\n</package>"
        )
        toc_ncx = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
            f'<head><meta name="dtb:uid" content="{uid}"/></head>\n'
            f'<docTitle><text>{esc(novel.title)}</text></docTitle>\n<navMap>\n'
            + "\n".join(ncx_items) + "\n</navMap>\n</ncx>"
        )
        container = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>'
        )

        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as z:
            # mimetype 必须是第一个条目且不压缩
            z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", container)
            z.writestr("OEBPS/content.opf", content_opf)
            z.writestr("OEBPS/toc.ncx", toc_ncx)
            for path, data in files:
                z.writestr(path, data)
        print(f"[+] EPUB 已保存: {epub_path}（{len(chapters)} 章）")


# ============================================================
#  关键词搜索（需提供站点搜索入口；结果解析为通用规则，失败时明确提示而非臆造）
# ============================================================

def parse_search_results(html_text: str, base_url: str, limit: int = 30):
    """从搜索结果页通用解析书籍链接：链接文本像书名、href 像书籍目录页。"""
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    results, seen = [], set()
    book_href = re.compile(r"(/\d+/?$)|(book|novel|/\d+\.s?html?$)", re.IGNORECASE)
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href = a["href"].strip()
        if not title or len(title) < 2 or len(title) > 60:
            continue
        if not book_href.search(href):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "url": url})
        if len(results) >= limit:
            break
    return results


async def search_books(keyword: str, search_url: str, timeout: int = 15, proxy: str = None):
    """按站点搜索入口检索。search_url 用 {q} 占位关键词，如 https://site/search?q={q}。"""
    if aiohttp is None:
        raise RuntimeError("缺少 aiohttp，请先 pip install aiohttp beautifulsoup4")
    if not search_url or "{q}" not in search_url:
        raise ValueError("需要用 --search-site 指定含 {q} 占位的搜索入口 URL")
    from urllib.parse import quote
    url = search_url.replace("{q}", quote(keyword, encoding="utf-8"))
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout_obj, proxy=proxy or None) as resp:
            if resp.status != 200:
                raise RuntimeError(f"搜索请求失败 HTTP {resp.status}")
            raw = await resp.read()
    return parse_search_results(decode_html(raw), url)


# ============================================================
#  命令行接口
# ============================================================

def check_dependencies():
    missing = []
    if aiohttp is None:
        missing.append("aiohttp")
    if BeautifulSoup is None:
        missing.append("beautifulsoup4")
    if missing:
        print(f"[!] 缺少依赖库: {', '.join(missing)}")
        print(f"    请运行: pip install {' '.join(missing)}")
        return False
    return True


def run_pipeline_step(script_name: str, args: list, cwd: str = None):
    """运行流水线中的下一步脚本（fix_text.py / build_data.py）"""
    import subprocess
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        print(f"[!] 未找到 {script_name}，跳过此步骤")
        return False
    cmd = [sys.executable, str(script_path)] + args
    print(f"\n[*] 运行: {script_name} {' '.join(args)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode == 0


def run_one(url, args):
    """下载单本小说，并按参数执行后续修正/构建流水线，返回 Novel。"""
    adapter = get_adapter(args.adapter, url)
    print(f"[*] 使用适配器: {adapter.name}")
    crawler = NovelCrawler(
        adapter=adapter,
        delay=args.delay,
        max_concurrent=args.concurrent,
        timeout=args.timeout,
        max_retries=args.retries,
        output_dir=args.output,
        encoding=args.encoding,
        auto_fix=args.fix or args.web,
        proxy=args.proxy,
        user_agent=args.ua,
        referer=args.referer,
        cookie=args.cookie,
        export_format=args.format,
        merge_pages=not args.no_merge_pages,
    )
    novel = asyncio.run(crawler.crawl(url))

    if args.fix or args.web:
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", novel.title)
        txt_path = Path(args.output) / f"{safe_title}.txt"
        if txt_path.exists():
            run_pipeline_step("fix_text.py", [str(txt_path)])
    if args.build or args.web:
        web_dir = args.web_dir or str(Path(__file__).parent)
        run_pipeline_step("build_data.py", ["-i", args.output, "-o", web_dir])
        print(f"\n[+] 完成！刷新 {web_dir} 中的 biquge.html 即可阅读")
    return novel


def main():
    parser = argparse.ArgumentParser(
        description="小说爬虫 v3.0 - 多站点小说下载/搜索/批量工具（仅供学习使用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 自动检测站点并下载（推荐）
  python novel_crawler.py -u https://www.guoxuehuicui.com/novel/sanguoyanyi/

  # 导出 EPUB 电子书（或 txt / both）
  python novel_crawler.py -u URL --format epub

  # 增量更新（只补新章，其余走缓存）
  python novel_crawler.py -u URL --update

  # 批量下载：urls.txt 一行一个目录页
  python novel_crawler.py -l urls.txt

  # 关键词搜索（需给出该站搜索入口，{q} 为关键词占位）
  python novel_crawler.py --search 三国演义 --search-site "https://example.com/search?q={q}"

  # 走代理 / 自定义 UA、Referer、Cookie
  python novel_crawler.py -u URL --proxy http://127.0.0.1:7890 --ua "Mozilla/5.0 ..."

  # 一键流程：爬取 + 文本修正 + 生成网页数据
  python novel_crawler.py -u URL --web

法律提示: 请遵守目标网站 robots.txt，仅下载公有领域或已授权内容。
        """,
    )
    parser.add_argument("-u", "--url", required=False, help="小说目录页 URL")
    parser.add_argument(
        "-a", "--adapter",
        choices=["auto", "biquge", "generic", "guoxue"],
        default="auto",
        help="站点适配器: auto=自动检测(默认), biquge, guoxue, generic",
    )
    parser.add_argument("-l", "--list", dest="list_file", default=None,
                        help="批量下载清单文件（一行一个目录页 URL，# 开头为注释）")
    parser.add_argument("-o", "--output", default="novels", help="输出目录 (默认: novels)")
    parser.add_argument("-d", "--delay", type=float, default=1.0, help="每章请求间隔秒数 (默认: 1.0)")
    parser.add_argument("-c", "--concurrent", type=int, default=3, help="最大并发数 (默认: 3)")
    parser.add_argument("-t", "--timeout", type=int, default=15, help="请求超时秒数 (默认: 15)")
    parser.add_argument("-r", "--retries", type=int, default=3, help="失败重试次数 (默认: 3)")
    parser.add_argument("-e", "--encoding", default=None, help="指定页面编码 (如 gbk, utf-8)，默认自动检测")
    parser.add_argument("--format", choices=["txt", "epub", "both"], default="txt",
                        help="导出格式: txt(默认) / epub 电子书 / both 同时导出")
    parser.add_argument("--update", action="store_true", help="增量更新：已下载章节走缓存，只补新章")
    parser.add_argument("--no-merge-pages", action="store_true", help="关闭章节分页自动合并")
    parser.add_argument("--proxy", default=None, help="HTTP/SOCKS 代理，如 http://127.0.0.1:7890")
    parser.add_argument("--ua", default=None, help="自定义 User-Agent")
    parser.add_argument("--referer", default=None, help="自定义 Referer")
    parser.add_argument("--cookie", default=None, help="自定义 Cookie 字符串")
    parser.add_argument("--search", dest="search_kw", default=None, help="按关键词搜索书籍（需配合 --search-site）")
    parser.add_argument("--search-site", dest="search_site", default=None,
                        help='站点搜索入口，用 {q} 占位关键词，如 "https://x.com/search?q={q}"')
    parser.add_argument("--fix", action="store_true", help="爬取后自动运行 fix_text.py 修正文本")
    parser.add_argument("--build", action="store_true", help="爬取后自动运行 build_data.py 生成网页数据")
    parser.add_argument("--web", action="store_true", help="一键流程: 爬取 + 修正 + 生成网页数据 (等价于 --fix --build)")
    parser.add_argument("--web-dir", default=None, help="网页数据输出目录 (默认: 爬虫脚本所在目录)")

    args = parser.parse_args()

    print("=" * 55)
    print("  小说爬虫 Novel Crawler v3.0")
    print("  仅供学习使用，请遵守相关法律法规")
    print("=" * 55)
    print()

    if not check_dependencies():
        sys.exit(1)

    # 模式一：关键词搜索
    if args.search_kw:
        if not args.search_site:
            print("[!] 搜索需要 --search-site 指定站点搜索入口（其中用 {q} 作为关键词占位）")
            sys.exit(2)
        try:
            results = asyncio.run(search_books(args.search_kw, args.search_site,
                                               timeout=args.timeout, proxy=args.proxy))
        except Exception as e:
            print(f"[!] 搜索失败: {e}")
            print("    提示：各站搜索接口不同，可在浏览器打开该站搜索页后，把地址中的关键词换成 {q} 再试")
            sys.exit(1)
        if not results:
            print("[*] 未解析到书籍结果（该站结构可能不受通用规则支持，可直接用 -u 传目录页）")
            return
        print(f"[+] 找到 {len(results)} 条结果：")
        for i, it in enumerate(results, 1):
            print(f"  {i:>2}. {it['title']}  ->  {it['url']}")
        return

    # 汇总待下载 URL
    urls = []
    if args.list_file:
        p = Path(args.list_file)
        if not p.exists():
            print(f"[!] 清单文件不存在: {args.list_file}")
            sys.exit(1)
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line.split()[0])
    if args.url:
        urls.append(args.url)
    if not urls:
        parser.error("请用 -u 指定目录页 URL，或用 -l 指定批量清单，或用 --search 搜索")

    ok_n, fail_n = 0, 0
    for idx, url in enumerate(urls, 1):
        if len(urls) > 1:
            print(f"\n{'#' * 20} 批量进度 {idx}/{len(urls)}: {url} {'#' * 20}")
        try:
            run_one(url, args)
            ok_n += 1
        except KeyboardInterrupt:
            print("\n[!] 用户中断，已下载的章节已缓存，重新运行可续传")
            sys.exit(1)
        except Exception as e:
            fail_n += 1
            print(f"\n[!] 下载失败 ({url}): {e}")
    if len(urls) > 1:
        print(f"\n[*] 批量结束：成功 {ok_n} 本，失败 {fail_n} 本")
        if fail_n:
            sys.exit(1)


if __name__ == "__main__":
    main()
