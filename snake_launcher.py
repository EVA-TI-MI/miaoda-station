#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
妙搭小站 - EXE 启动器
使用 pywebview 创建原生窗口加载首页（贪吃蛇 + 笔趣阁）
"""
import os
import sys
import webview


def resource_path(relative):
    """获取资源路径（兼容开发环境和 PyInstaller 打包环境）"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def main():
    index_path = resource_path('index.html')
    if not os.path.exists(index_path):
        print(f"错误: 找不到首页文件 {index_path}")
        sys.exit(1)

    html_url = 'file:///' + index_path.replace('\\', '/')

    window = webview.create_window(
        title='妙搭小站',
        url=html_url,
        width=1000,
        height=750,
        min_size=(500, 600),
        resizable=True,
        background_color='#0f0d08',
    )

    webview.start(debug=False)


if __name__ == '__main__':
    main()
