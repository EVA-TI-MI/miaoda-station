#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cleanup_shelf.py - 根据笔趣阁书架状态清理本地小说缓存

工作流程：
  1. 在笔趣阁网页「书架」页面点击「📤 导出书架状态」，下载 bookshelf_state.json
  2. 将 bookshelf_state.json 放到本脚本同目录（或用 -s 指定路径）
  3. 运行本脚本，它会：
     - 对比书架中的爬虫小说与 novels/ 目录中的本地文件
     - 删除不在书架中的小说对应的缓存目录、TXT 和 meta.json
     - 自动调用 build_data.py 重新生成 novels_data.js
  4. 刷新 biquge.html 即可看到更新

用法：
  python cleanup_shelf.py                          # 默认读取 bookshelf_state.json
  python cleanup_shelf.py -s D:\\path\\state.json  # 指定状态文件
  python cleanup_shelf.py -n novels                # 指定小说目录
  python cleanup_shelf.py -o D:\\tanlan            # 指定网页目录（novels_data.js 输出位置）
  python cleanup_shelf.py --dry-run                # 仅预览将要删除的文件，不实际删除
  python cleanup_shelf.py --no-rebuild             # 删除后不重新生成 novels_data.js
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def safe_title(title: str) -> str:
    """与 novel_crawler.py 一致的文件名安全处理"""
    return re.sub(r'[\\/:*?"<>|]', '_', title)


def scan_local_novels(novels_dir: Path) -> dict:
    """
    扫描小说目录，返回 {safe_title: {'cache': Path, 'txt': Path, 'meta': Path, 'title': str}}
    """
    novels = {}

    # 1. 通过 meta.json 识别（最可靠，内含真实书名）
    for meta_file in novels_dir.glob('*.meta.json'):
        st = meta_file.name.replace('.meta.json', '')
        entry = novels.setdefault(st, {'title': st})
        entry['meta'] = meta_file
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            if meta.get('title'):
                entry['title'] = meta['title']
                # 用真实书名重新计算 safe_title，确保与书架导出一致
                real_st = safe_title(meta['title'])
                if real_st != st:
                    novels[real_st] = novels.pop(st)
                    novels[real_st]['meta'] = meta_file
                    st = real_st
        except (json.JSONDecodeError, OSError):
            pass

    # 2. 扫描 TXT 文件
    for txt_file in novels_dir.glob('*.txt'):
        st = txt_file.stem
        entry = novels.setdefault(st, {'title': st})
        entry['txt'] = txt_file

    # 3. 扫描缓存目录（.{title}_cache）
    for cache_dir in novels_dir.glob('.*_cache'):
        # 去掉开头的 . 和结尾的 _cache
        st = cache_dir.name[1:-6] if cache_dir.name.endswith('_cache') else cache_dir.name[1:]
        entry = novels.setdefault(st, {'title': st})
        entry['cache'] = cache_dir

    return novels


def main():
    parser = argparse.ArgumentParser(
        description='根据笔趣阁书架状态清理本地小说缓存',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-s', '--state', default='bookshelf_state.json',
                        help='书架状态 JSON 文件路径 (默认: bookshelf_state.json)')
    parser.add_argument('-n', '--novels-dir', default='novels',
                        help='小说文件目录 (默认: novels)')
    parser.add_argument('-o', '--web-dir', default='.',
                        help='网页目录，用于重新生成 novels_data.js (默认: 当前目录)')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅预览将要删除的文件，不实际删除')
    parser.add_argument('--no-rebuild', action='store_true',
                        help='删除后不重新生成 novels_data.js')
    args = parser.parse_args()

    # ---- 读取书架状态 ----
    state_path = Path(args.state)
    if not state_path.exists():
        print(f'[!] 未找到书架状态文件: {state_path}')
        print()
        print('    请先在笔趣阁网页的「书架」页面点击「📤 导出书架状态」按钮，')
        print('    将下载的 bookshelf_state.json 放到本脚本同目录后重试。')
        print('    也可以用 -s 参数指定文件路径。')
        sys.exit(1)

    with open(state_path, 'r', encoding='utf-8-sig') as f:
        state = json.load(f)

    shelf_books = state.get('shelfCrawlerBooks', [])
    shelf_titles = {b['title'] for b in shelf_books}
    shelf_safe_titles = {safe_title(t) for t in shelf_titles}

    export_time = state.get('exportTime', '未知')
    print(f'[*] 书架状态导出时间: {export_time}')
    print(f'[*] 书架中有 {len(shelf_titles)} 本爬虫小说:')
    for t in sorted(shelf_titles):
        print(f'    ✓ {t}')

    # ---- 扫描本地目录 ----
    novels_dir = Path(args.novels_dir)
    if not novels_dir.exists():
        print(f'\n[!] 小说目录不存在: {novels_dir}')
        sys.exit(1)

    local_novels = scan_local_novels(novels_dir)
    print(f'\n[*] 本地目录中发现 {len(local_novels)} 本小说')

    # ---- 找出需要删除的 ----
    to_delete = []
    for st, files in local_novels.items():
        if st not in shelf_safe_titles:
            to_delete.append((files.get('title', st), files))

    if not to_delete:
        print('\n[+] 没有需要清理的小说，所有本地小说都在书架中')
        return

    print(f'\n[*] 发现 {len(to_delete)} 本不在书架中的小说，将清理其文件：')
    total_files = 0
    for title, files in to_delete:
        print(f'    - 《{title}》')
        for key in ('cache', 'txt', 'meta'):
            if key in files:
                print(f'        {files[key]}')
                total_files += 1

    if args.dry_run:
        print(f'\n[*] 预览模式（--dry-run），共 {total_files} 个文件/目录将被删除，未实际执行')
        return

    # ---- 确认删除 ----
    print(f'\n[*] 即将删除 {total_files} 个文件/目录')
    try:
        answer = input('    确认删除？(y/N): ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ''
        print()
    if answer not in ('y', 'yes'):
        print('[*] 已取消')
        return

    # ---- 执行删除 ----
    deleted_count = 0
    for title, files in to_delete:
        for key in ('cache', 'txt', 'meta'):
            f = files.get(key)
            if not f:
                continue
            try:
                if f.is_dir():
                    shutil.rmtree(f)
                else:
                    f.unlink()
                print(f'    已删除: {f.name}')
                deleted_count += 1
            except OSError as e:
                print(f'    [!] 删除失败: {f} - {e}')

    print(f'\n[+] 共删除 {deleted_count} 个文件/目录')

    # ---- 重新生成 novels_data.js ----
    if args.no_rebuild:
        return

    build_script = Path(__file__).parent / 'build_data.py'
    if not build_script.exists():
        print(f'[!] 未找到 build_data.py，请手动重新生成 novels_data.js')
        return

    print(f'\n[*] 正在重新生成 novels_data.js ...')
    cmd = [sys.executable, str(build_script), '-i', str(novels_dir), '-o', args.web_dir]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print('[+] novels_data.js 已更新，刷新 biquge.html 即可生效')
    else:
        print('[!] novels_data.js 重新生成失败，请手动运行 build_data.py')


if __name__ == '__main__':
    main()
