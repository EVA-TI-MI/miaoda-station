# 妙搭小站 (Miaoda Station)

弈境棋院（AI 围棋 / AI 中国象棋 / AI 国际象棋 / AI 五子棋）+ 霓虹贪吃蛇 + 墨渊阁小说阅读器。
基于 HTML5 Canvas + 原生 JavaScript 开发，**所有 AI 均在浏览器本地计算，无需后端、可离线运行（PWA）**，
可通过 pywebview 打包为 Windows 桌面应用，也可直接在浏览器中打开。

## 五大功能模块

### 1. AI 围棋 · 弈境（`go.html`）
- 完整规则：连通块气数计算、自动提子、禁着点（自杀）拦截、打劫（局面签名防回提）
- 9 / 13 / 19 路棋盘，让子（0–9 子）、贴目（7.5/6.5/0）
- AI：蒙特卡洛树搜索（MCTS，选择—扩展—随机模拟—回传），四档难度按时间预算迭代；含吃子优先的模拟策略
- 停一手（双方连停终局）、认输、终局标记死子 + 中国规则数子、势力可视化
- 标准 SGF 棋谱导出/复制、悔棋/重做、AI 提示、提子统计、计时、战绩、自动续局、棋盘皮肤

### 2. 象棋（`chess.html` 为二级选择页，内含两种）
进入象棋模块后可选择中国象棋或国际象棋，两者操作体验一致。

#### 2.1 AI 中国象棋 · 楚河（`xiangqi.html`）
- 完整规则：七兵种走法、蹩马腿、塞象眼、象不过河、九宫限制、飞将照面拦截、合法着法过滤
- 将军 / 将死 / 困毙判定（困毙亦负）
- AI：子力价值 + 位置表（PST）、Negamax + Alpha-Beta 剪枝、着法排序（MVV-LFA）、迭代加深 + 时间预算，四档难度
- 合法走法高亮、AI 提示、悔棋/重做、翻转棋盘、执红执黑、中文标准着法棋谱、双方吃子陈列与子力优势条
- 内置经典残局挑战、棋谱导出、计时、战绩、自动续局、棋盘皮肤

#### 2.2 AI 国际象棋（`intchess.html`）
- 完整规则：兵首步双走、斜吃、**吃过路兵（en passant）**、到底线**升变**（后/车/象/马，默认升后）；马、象、车、后、王的标准走法
- **王车易位**（长/短易位，校验空格、王不在被将、途经格不被攻击）；几何攻击判定与合法着法过滤
- 将死 / 逼和（无子可动和棋）/ 子力不足和棋判定
- AI：子力价值 + 六张位置表（PST）、Negamax + Alpha-Beta + 迭代加深，四档难度
- 代数记谱（SAN：O-O / O-O-O / 吃子 x / 升变 =Q / 将 + / 将杀 #）、合法走法高亮、悔棋/重做、AI 提示、执白执黑、吃子陈列与子力优势条、棋谱导出、计时、战绩、自动续局

### 3. AI 五子棋 · 连珠（`gomoku.html`）
- 15 路标准盘，五连判定；可选连珠禁手（黑方双三 / 双四 / 长连）
- AI：活四/冲四/活三/活二等棋型评估 + Minimax（Negamax）+ Alpha-Beta 剪枝 + 候选着法排序，四档难度
- 人机 / 双人 / AI 观战三模式、执黑执白、落子手数编号、AI 杀点提示、悔棋（人机连撤两步）/重做
- 坐标棋谱导出/复制、局势条、计时、战绩、自动续局、棋盘皮肤

### 4. 霓虹贪吃蛇（`snake.html`，参考开源项目增强）
- 16 款皮肤（V 键逆时针切换）、三种难度、穿墙模式、多档地图/窗口尺寸、本地排行榜、用户系统、快捷键操作
- **随机道具**：减速（时间变慢）、金身（短时穿越自身与障碍）、缩身（立即缩短 4 节），道具限时出现
- **障碍物模式**：可开关的随机障碍布局（避开出生区），增加走位挑战
- **AI 自动演示**：BFS 最短寻路 + 洪水填充逃生校验（保证安全活动空间），随时一键接管/交还（i 键）
- 局内统计：食物数、用时、长度、分数 HUD 实时展示；随分数自动加速

### 5. 墨渊阁小说阅读器（`biquge.html`，既有）
- 在线书库浏览/搜索/章节阅读、书架收藏、进度保存、字体主题调节
- 有声书朗读（多音色、语速、逐段高亮、自动连播）、爬虫下载离线阅读

## 棋类统一能力
人机 / 双人 / AI 观战三模式；四档 AI；悔棋、重做、提示、新开、换边；实时棋谱与导出；
对局计时、音效、棋盘皮肤、最后落子标记、坐标、移动端点触响应；localStorage 战绩与自动续局；
统一深色「棋院」视觉、PWA 离线缓存、源码保护、快捷键（N 新开 / Z 悔棋 / Y 重做 / H 提示）。

## 项目结构

```
├── index.html           # 导航首页（五大模块 + 介绍文章）
├── go.html              # AI 围棋（单文件，内嵌引擎/AI/样式）
├── chess.html           # 象棋二级选择页（中国象棋 / 国际象棋）
├── xiangqi.html         # AI 中国象棋（单文件）
├── intchess.html        # AI 国际象棋（单文件）
├── gomoku.html          # AI 五子棋（单文件）
├── snake.html           # 霓虹贪吃蛇
├── biquge.html          # 墨渊阁小说阅读器
├── novels_data.js       # 小说数据（由爬虫生成）
├── 棋类功能规划.md       # 开源调研、功能矩阵与选型决策
├── sw.js                # Service Worker（PWA 离线支持）
├── manifest.json        # PWA 清单
├── icon-192/512.png     # 应用图标
├── snake_launcher.py    # pywebview 桌面启动器
├── novel_crawler.py / build_data.py / cleanup_shelf.py / fix_text.py / validate_data.py
├── requirements.txt
└── 爬虫使用说明.md
```

## 运行

### 浏览器直接运行
用浏览器打开 `index.html` 即可；四种棋的 AI 全部本地计算，断网也能玩。

### 桌面应用（Windows）
```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --noconfirm --name "妙搭小站" ^
  --add-data "index.html;." --add-data "go.html;." --add-data "chess.html;." ^
  --add-data "xiangqi.html;." --add-data "intchess.html;." ^
  --add-data "gomoku.html;." --add-data "snake.html;." --add-data "biquge.html;." ^
  --add-data "sw.js;." --add-data "manifest.json;." ^
  --add-data "icon-192.png;." --add-data "icon-512.png;." snake_launcher.py
```

### 小说爬虫
```bash
python novel_crawler.py -u <小说目录页URL> --build
```
详见 `爬虫使用说明.md`。

## 技术栈
- 前端：HTML5 Canvas、原生 JavaScript（无框架依赖）
- 棋类 AI：围棋 MCTS；中国象棋/国际象棋 Negamax + Alpha-Beta + 迭代加深（PST 评估）；五子棋棋型评估 + Minimax + Alpha-Beta
- 桌面：pywebview + PyInstaller
- 爬虫：Python requests + BeautifulSoup
- 部署：GitHub Pages（PWA）

## 在线访问
[https://eva-ti-mi.github.io/games/](https://eva-ti-mi.github.io/games/)

## 版本
- V4.0.0：弈境棋院四棋（AI 围棋 / 中国象棋 / 国际象棋 / 五子棋）；象棋模块拆为二级选择页（中国象棋 `xiangqi.html`、国际象棋 `intchess.html`）；贪吃蛇新增随机道具、障碍物模式与 BFS+洪水填充 AI 自动演示、局内统计；首页介绍文章同步适配，PWA 缓存升级 v19
- V4.0.0（前序）：弈境棋院三弈上线（AI 围棋 / 中国象棋 / 五子棋），首页升级为五大功能模块并新增介绍文章，PWA 缓存同步更新
- V3.7：彩虹皮肤流动变色、发布流程修复（历史版本）
