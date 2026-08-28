#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 novels_data.js 数据完整性"""
import argparse
import json
import re
import sys
from pathlib import Path


def validate(path: Path):
    if not path.exists():
        print(f"[!] 文件不存在: {path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()

    m = re.search(r'window\.NOVELS_DATA\s*=\s*(\[.*\]);', txt, re.DOTALL)
    if not m:
        print("[!] 无法解析 novels_data.js：未找到 window.NOVELS_DATA 数组")
        sys.exit(1)

    data = json.loads(m.group(1))
    if not data:
        print("[!] 数据为空")
        sys.exit(1)

    print(f"共 {len(data)} 本小说\n")
    all_ok = True

    for idx, b in enumerate(data):
        title = b.get('title', '未知')
        author = b.get('author', '未知')
        chapters = b.get('chapters', 0)
        real = b.get('realContent', [])

        status = "✓" if chapters == len(real) and chapters > 0 else "✗"
        if chapters != len(real) or chapters == 0:
            all_ok = False

        print(f"  {status} [{idx+1}] {title} / {author}")
        print(f"      章节数: {chapters}, realContent: {len(real)}")

        # 检查空章节
        empty = [i+1 for i, ch in enumerate(real) if not ch.get('paragraphs')]
        if empty:
            all_ok = False
            print(f"      ✗ 空章节: {empty[:10]}{'...' if len(empty)>10 else ''}")

        # 显示首章信息
        if real:
            ch1 = real[0]
            print(f"      首章: {ch1.get('title','?')} ({len(ch1.get('paragraphs',[]))} 段)")

        # 总字数
        total = sum(len(p) for ch in real for p in ch.get('paragraphs', []))
        print(f"      正文字数: {total} ({total/10000:.1f}万)")
        print()

    if all_ok:
        print("=== 所有数据校验通过 ✓ ===")
    else:
        print("=== 存在问题，请检查上方 ✗ 项 ===")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='验证 novels_data.js 数据完整性')
    parser.add_argument('path', nargs='?', default='novels_data.js',
                        help='novels_data.js 路径 (默认: 当前目录)')
    args = parser.parse_args()
    validate(Path(args.path))


if __name__ == '__main__':
    main()
