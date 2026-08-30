# 妙搭小站 (Miaoda Station)

霓虹贪吃蛇 + 笔趣阁小说阅读器，基于 HTML5 Canvas + 原生 JavaScript 开发，可通过 pywebview 打包为 Windows 桌面应用，也可直接在浏览器中运行。

## 功能

### 霓虹贪吃蛇
- 16 款皮肤：经典原色、机甲、二次元、水墨、3D、线条一次元、像素加工版、赛博朋克等
- 皮肤分组：左侧 3D 风格，右侧经典/像素风格
- 三种难度（休闲/普通/极速）、穿墙模式、三种地图尺寸、三种窗口尺寸
- 本地排行榜、用户系统、最高分记录
- 快捷键：`空格` 开始/暂停、`O` 设置、`C` 顺时针换肤、`V` 逆时针换肤、`H` 首页、`L` 排行榜
- 双击齿轮图标快速进入/退出设置

### 笔趣阁小说阅读器
- 在线书库浏览、搜索、章节阅读
- 书架收藏/喜欢功能，数据本地存储
- 阅读进度自动保存、字体/主题调节
- 有声书朗读：多音色选择、语速调节、逐段高亮、自动连播下一章、暂停/停止
- 爬虫脚本支持下载小说到本地离线阅读
- 删除书架小说时自动清理对应缓存

## 项目结构

```
├── index.html           # 导航首页（选择贪吃蛇/笔趣阁）
├── snake.html           # 霓虹贪吃蛇游戏
├── biquge.html          # 笔趣阁小说阅读器
├── novels_data.js       # 小说数据（由爬虫生成）
├── sw.js                # Service Worker（PWA 离线支持）
├── manifest.json        # PWA 清单
├── icon-192/512.png     # 应用图标
├── snake_launcher.py    # pywebview 桌面启动器
├── novel_crawler.py     # 小说爬虫主程序
├── build_data.py        # 小说数据构建工具
├── cleanup_shelf.py     # 书架缓存清理工具
├── fix_text.py          # 文本修复工具
├── validate_data.py     # 数据验证工具
├── requirements.txt     # Python 依赖
└── 爬虫使用说明.md       # 爬虫使用文档
```

## 运行

### 浏览器直接运行
用浏览器打开 `index.html` 即可。

### 桌面应用（Windows）
```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --noconfirm --name "霓虹贪吃蛇" ^
  --add-data "snake.html;." --add-data "biquge.html;." ^
  --add-data "index.html;." --add-data "sw.js;." ^
  --add-data "manifest.json;." --add-data "icon-192.png;." ^
  --add-data "icon-512.png;." snake_launcher.py
```
生成的 EXE 在 `dist/` 目录。

### 小说爬虫
```bash
pip install -r requirements.txt
python novel_crawler.py -u <小说目录页URL> --build
```
详见 `爬虫使用说明.md`。

## 技术栈
- 前端：HTML5 Canvas、原生 JavaScript（无框架依赖）
- 桌面：pywebview + PyInstaller
- 爬虫：Python requests + BeautifulSoup
- 部署：GitHub Pages（PWA）

## 在线访问
[https://eva-ti-mi.github.io/games/](https://eva-ti-mi.github.io/games/)

## 版本
当前版本：V3.6（新增有声书朗读）
