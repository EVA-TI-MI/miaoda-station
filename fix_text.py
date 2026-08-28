#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_text.py - 修正爬取文本中的源站OCR/编码错误

国学荟萃等站点的文本存在以下问题：
1. "躁"系统性替换"操"（如"曹躁"代"曹操"）
2. "-"替换生僻字（如"荀-"代"荀彧"、"李-"代"李傕"）
3. 个别OCR错字（如"荒滢"代"荒淫"、"牢蚤"代"牢骚"）

用法:
  python fix_text.py novels/三国演义.txt
  python fix_text.py novels/  # 批量处理目录下所有txt
"""

import re
import sys
from pathlib import Path


def fix_text(text: str) -> str:
    """应用所有修正规则"""

    # === 1. 系统性字符替换 ===

    # "躁" → "操"（源站系统性替换）
    # 先保护合法词，再全局替换，最后恢复
    # 注意：不保护"躁动"——经核查全文中"躁动"仅出现在"曹躁动静"中，属误替换
    _legit_zao = {'急躁': '\x001', '浮躁': '\x002', '焦躁': '\x003', '暴躁': '\x004'}
    for word, placeholder in _legit_zao.items():
        text = text.replace(word, placeholder)
    text = text.replace('躁', '操')
    for word, placeholder in _legit_zao.items():
        text = text.replace(placeholder, word)

    # "滢" → "淫"（荒滢 → 荒淫）
    text = text.replace('荒滢', '荒淫')

    # "牢蚤" → "牢骚"
    text = text.replace('牢蚤', '牢骚')

    # "貌貅" → "貔貅"
    text = text.replace('貌貅', '貔貅')

    # === 2. 生僻字 "-" 替换（基于上下文推断） ===

    # 荀- → 荀彧（三国演义中"荀-"说话/进谏的几乎都是荀彧）
    text = text.replace('荀-', '荀彧')

    # 李- → 李傕（董卓部将，后与郭汜混战）
    text = text.replace('李-', '李傕')

    # 费- → 费祎（蜀汉后期大臣）
    text = text.replace('费-', '费祎')

    # 朱- → 朱儁（汉末名将，讨伐黄巾）
    text = text.replace('朱-', '朱儁')

    # === 3. 夏侯- 上下文判定（惇/渊/楙/霸等） ===

    # 夏侯惇特征：左目中箭、拔矢啖睛、博望坡、被劫质、完体将军
    xiahou_dun = [
        '夏侯-左目', '夏侯-拔矢', '夏侯-啖睛', '夏侯-搠', '夏侯-为先锋',
        '夏侯-引军', '夏侯-引兵', '夏侯-领兵', '夏侯-大军', '夏侯-分两路',
        '夏侯-与夏侯', '夏侯-之侄', '夏侯-称为完', '夏侯-天下奇',
        '夏侯-治兵', '夏侯-所领', '夏侯-部将秦', '夏侯-奉曹',
        '夏侯-戴金盔', '夏侯-复整金', '夏侯-冒烟突', '夏侯-收拾残',
        '夏侯-败回', '夏侯-为第三', '夏侯-大半人', '夏侯-押耿',
        '夏侯-尽杀五', '夏侯-入帐', '夏侯-寨内', '夏侯-也',
        '夏侯-为子', '夏侯-叱曰', '夏侯-辞了', '夏侯-乃膏粱',
        '夏侯-若闻', '夏侯-在长安', '夏侯-慌忙', '夏侯-先走',
        '夏侯-在山上', '夏侯-乃无谋', '夏侯-望南安', '夏侯-乃魏之',
        '夏侯-处', '夏侯-府下', '夏侯-之心', '夏侯-措手',
        '夏侯-于马上', '夏侯-囚于车', '夏侯-困在南', '夏侯-至帐下',
        '夏侯-与马遵', '夏侯-商议', '夏侯-数次', '夏侯-大不相',
        '夏侯-驸马', '夏侯-所可比', '夏侯-抵敌', '夏侯-拍马',
        '夏侯-应声', '夏侯-赶来', '夏侯-接见', '夏侯-引许褚',
        '夏侯-往探', '夏侯-孤力', '夏侯-屯兵', '夏侯-战不三',
        '夏侯-损其', '夏侯-既杀', '夏侯-又到', '夏侯-交战',
        '夏侯-又截', '夏侯-领兵守', '夏侯-知之', '夏侯-大叫',
        '夏侯-领三百', '夏侯-挺枪', '夏侯-只得', '夏侯-领军',
        '夏侯-发书', '夏侯-引军抄', '夏侯-已打破', '夏侯-军势',
        '夏侯-引众人', '夏侯-进曰', '夏侯-为都督', '夏侯-引兵十',
        '夏侯-与于禁', '夏侯-从后追', '夏侯-笑谓', '夏侯-只顾催',
        '夏侯-正走', '夏侯-猛省', '夏侯-虽败', '夏侯-在襄阳',
        '夏侯-未至', '夏侯-亦至', '夏侯-领兵三', '夏侯-大惊',
        '夏侯-曰', '夏侯-于路截', '夏侯-引一大', '夏侯-引兵到',
        '夏侯-挺枪跃',
    ]
    for pat in xiahou_dun:
        text = text.replace(pat, pat.replace('夏侯-', '夏侯惇'))

    # 夏侯渊特征：定军山、黄忠、妙才、守汉中
    xiahou_yuan = [
        '夏侯-守汉中', '夏侯-定军', '夏侯-被黄忠', '夏侯-妙才',
    ]
    for pat in xiahou_yuan:
        text = text.replace(pat, pat.replace('夏侯-', '夏侯渊'))

    # 剩余的"夏侯-"统一替换为"夏侯惇"（他出场更早更多）
    text = text.replace('夏侯-', '夏侯惇')

    # === 4. 王- 上下文判定 ===

    # 王垕（粮官，曹操借头）特征：仓官、小斛、禀操
    wang_hou = ['王-人禀', '王-故行小', '王-耶']
    for pat in wang_hou:
        text = text.replace(pat, pat.replace('王-', '王垕'))

    # 王濬（西晋灭吴大将）特征：楼船、上疏伐吴、报捷
    wang_jun = ['王-上疏', '王-楼船', '王-遣人驰', '王-等奉了', '王-上表报', '王-等家']
    for pat in wang_jun:
        text = text.replace(pat, pat.replace('王-', '王濬'))

    # 剩余"王-" → 王濬（最后一回的语境）
    text = text.replace('王-', '王濬')

    # === 5. 其他明确的人名替换 ===

    # 陈珪/陈登（徐州陈氏父子）
    text = text.replace('陈-父子', '陈珪父子')
    chen_gui = ['陈-又说吕布', '陈-守徐州', '陈-秩中二千石', '陈-曰：不可', '陈-居右']
    for pat in chen_gui:
        text = text.replace(pat, pat.replace('陈-', '陈珪'))

    # 金祎（汉臣，反曹起义）
    text = text.replace('金-', '金祎')

    # 金鈚箭
    text = text.replace('金祎箭', '金鈚箭')

    # 彭羕（蜀汉谋士）
    text = text.replace('彭-', '彭羕')

    # 段珪（十常侍之一）
    text = text.replace('段-', '段珪')

    # 孙綝（东吴权臣）
    text = text.replace('孙-', '孙綝')

    # 雍闿（南中叛将）
    text = text.replace('雍-', '雍闿')

    # 乐綝（乐进之子）
    text = text.replace('乐-', '乐綝')

    # 卫瓘（监军，收邓艾）
    text = text.replace('卫-', '卫瓘')

    # 丁廙（丁仪之弟）
    text = text.replace('丁-', '丁廙')

    # 毛玠（曹操东曹掾）
    text = text.replace('毛-', '毛玠')

    # 邓飏（曹爽"台中三狗"之一）
    text = text.replace('邓-', '邓飏')

    # 苏颙（魏将，追赵云中伏）
    text = text.replace('苏-', '苏颙')

    # 华核（吴中书丞）
    text = text.replace('华-', '华核')

    # 陶濬（吴将，降晋）
    text = text.replace('陶-', '陶濬')

    # 成倅（成济之弟）
    text = text.replace('成-', '成倅')

    # 蔡壎（蔡瑁之弟）
    text = text.replace('蔡-', '蔡壎')

    # 昌豨（泰山寇）
    text = text.replace('昌-', '昌豨')

    # 徐璆（得玉玺者）
    text = text.replace('徐-', '徐璆')

    # 全祎（全端之子，降魏）
    text = text.replace('全-', '全祎')

    # 马日磾（太傅）
    text = text.replace('马日-', '马日磾')

    # 青釭剑
    text = text.replace('青-剑', '青釭剑')
    text = text.replace('青-宝', '青釭宝')

    # 上邽（地名）
    text = text.replace('上-', '上邽')

    # 封谞（十常侍之一，黄巾内应）
    feng_xu = ['收封-等', '封-作乱']
    for pat in feng_xu:
        text = text.replace(pat, pat.replace('封-', '封谞'))

    # 刘璝（刘璋部将，守雒城）
    liu_gui = [
        '刘-曰：吾闻锦屏山', '刘-又问', '刘-等曰', '刘-再三',
        '刘-大喜', '刘-忙遣', '刘-听知', '刘-见后面',
        '刘-不打紧', '刘-守城', '刘-在城上', '杀刘-者',
    ]
    for pat in liu_gui:
        text = text.replace(pat, pat.replace('刘-', '刘璝'))

    # 张- 上下文判定（张郃/张昭/张纮/张闿/张顗等）
    # 张郃特征：与高览同往、守蒙头岩、巴西战张飞、战赵云
    zhang_he = [
        '张-曰：某与高览', '张-为参谋', '张-大笑曰：将军行兵',
        '张-引兵来了', '张-兵到', '张-守蒙头', '张-守后寨',
        '张-二将', '张-挺枪', '张-见了', '张-心慌',
        '张-出战', '张-大败', '张-杀条', '张-兵退',
        '张-自后', '张-分两', '张-离寨', '张-军来',
        '张-回寨', '张-连夜', '张-守把', '张-部兵',
        '张-等皆', '张-降', '令张-为先锋', '与张-商议',
        '谓张-曰', '非张-对手', '张-谏曰', '张-领军到',
        '张-守隘', '张-等引', '张-寨中', '张-急退',
        '张-后面', '张-等大', '张-等三', '张-等只',
        '张-等急', '张-等连', '张-等正', '张-等皆',
    ]
    for pat in zhang_he:
        text = text.replace(pat, pat.replace('张-', '张郃'))

    # 张昭特征：谏孙策/孙权、抚军中郎将
    zhang_zhao = [
        '张-谏曰：夫主将', '张-曰：主公', '张-曰：非',
        '张-等文官', '张-曰：可', '张-大',
    ]
    for pat in zhang_zhao:
        text = text.replace(pat, pat.replace('张-', '张昭'))

    # 张纮特征：回吴与张昭同理政事
    text = text.replace('张-回吴', '张纮回吴')

    # 张闿特征：杀曹嵩全家
    text = text.replace('张-杀尽曹嵩', '张闿杀尽曹嵩')
    text = text.replace('张-之恶', '张闿之恶')
    text = text.replace('张-不仁', '张闿不仁')

    # 马延、张顗
    text = text.replace('马延、张-', '马延、张顗')

    # 剩余张-统一替换为张郃（出场最多）
    text = text.replace('张-', '张郃')

    # === 6. 地名修正 ===

    # 郿坞（董卓行宫）
    mei_wu = ['归-坞', '往-坞', '至-坞', '于-坞', '守-坞']
    for pat in mei_wu:
        text = text.replace(pat, pat.replace('-', '郿'))

    # 猇亭（夷陵之战）
    xiao_ting = ['至-亭', '于-亭', '得-亭', '到-亭', '望-亭']
    for pat in xiao_ting:
        text = text.replace(pat, pat.replace('-', '猇'))

    # 段谷（姜维北伐兵败之地）
    text = text.replace('于-山谷', '于段谷')
    text = text.replace('往-山谷', '往段谷')

    # 淯水（曹操战张绣）
    text = text.replace('至-水下寨', '至淯水下寨')

    # 颍水/颍桥（毌丘俭文钦之叛）
    text = text.replace('于-水之上', '于颍水之上')
    text = text.replace('于-桥', '于颍桥')

    # 枹罕（陇西地名， near洮水）
    text = text.replace('望-罕', '望枹罕')

    # 琅琊（曹操父曹嵩避难地）
    text = text.replace('往-琊', '往琅琊')
    text = text.replace('隐居-琊', '隐居琅琊')

    # 越巂（蜀汉郡名）
    text = text.replace('越-四郡', '越巂四郡')
    text = text.replace('越-郡', '越巂郡')

    # 郿城（诸葛亮北伐取郿城）
    text = text.replace('取-城', '取郿城')
    text = text.replace('得-城', '得郿城')
    text = text.replace('守-城', '守郿城')

    # === 7. 其他明确的人名/词语 ===

    # 何颙（评曹操"安天下者必此人"）
    text = text.replace('何-见操', '何颙见操')

    # 郤正（蜀汉秘书郎，教刘禅应答）
    text = text.replace('郎-正', '郎郤正')
    text = text.replace('见-正', '见郤正')
    text = text.replace('如-正', '如郤正')

    # 万彧（吴丞相）
    text = text.replace('万-曰', '万彧曰')
    text = text.replace('万-为', '万彧为')

    # 刘寔（相国参军，预言钟邓必败）
    text = text.replace('刘-但笑', '刘寔但笑')
    text = text.replace('见-冷笑', '见寔冷笑')

    # 夏侯楙（夏侯渊子，字子休）
    text = text.replace('也-字子休', '也。楙字子休')

    # 司马伷（琅琊王，出涂中灭吴）
    text = text.replace('马-出涂中', '马伷出涂中')
    text = text.replace('马-并王戎', '马伷并王戎')

    # 李傕为大司马，信女巫
    text = text.replace('封-为大司马', '封傕为大司马')
    text = text.replace('-喜曰：此女巫', '傕喜曰：此女巫')

    # 乐綝家
    text = text.replace('杀至-家', '杀至綝家')

    # 蔡邕论灾异：霓堕鸡化
    text = text.replace('为-堕鸡化', '为霓堕鸡化')

    # 战栗失箸
    text = text.replace('战-失箸', '战栗失箸')
    text = text.replace('战-不能言', '战栗不能言')

    # 面如噀血
    text = text.replace('如-血', '如噀血')

    # 皆得躄疾（管辂卜筮故事）
    text = text.replace('得-疾', '得躄疾')

    # 碇石（船锚）
    text = text.replace('了-石', '了碇石')
    text = text.replace('起-石', '起碇石')

    # 锹镢（攻城器具）
    text = text.replace('锹-爬', '锹镢爬')
    text = text.replace('锹-军', '锹镢军')

    # 凄惶
    text = text.replace('也-惶', '也凄惶')

    # 金祎宅中，祎接入
    text = text.replace('宅中-接入', '宅中，祎接入')
    text = text.replace('归来-妻', '归来，祎妻')

    # 卫瓘引数十人
    text = text.replace('未起-引数十人', '未起，瓘引数十人')
    text = text.replace('来-叱武士', '来，瓘叱武士')

    # 孙綝杀戮
    text = text.replace('见-杀戮太过', '见綝杀戮太过')
    text = text.replace('召-赴席', '召綝赴席')

    # 王濬受降
    text = text.replace('请降-曰', '请降，濬曰')
    text = text.replace('归降-释其缚', '归降，濬释其缚')

    # 朱儁（讨黄巾）
    text = text.replace('出战-遣玄德', '出战，儁遣玄德')
    text = text.replace('交战-见弘', '交战，儁见弘')
    text = text.replace('投降-不许', '投降，儁不许')
    text = text.replace('讨之-奉诏', '讨之，儁奉诏')
    text = text.replace('计议-曰：彼用妖术', '计议，儁曰：彼用妖术')

    # 张郃（宕渠山之战）
    text = text.replace('搦战-在山上', '搦战，郃在山上')
    text = text.replace('出战-心慌', '出战，郃心慌')
    text = text.replace('挑战-又诈败', '挑战，郃又诈败')
    text = text.replace('乃魏延也-大怒', '乃魏延也。郃大怒')

    # 夏侯惇
    text = text.replace('退去-乃移', '退去，傕乃移')  # 李傕移驾
    text = text.replace('其事-自统兵', '其事，惇自统兵')
    text = text.replace('其事-曰：既然', '其事，惇曰：既然')
    text = text.replace('说知-曰：当用何计', '说知，惇曰：当用何计')
    text = text.replace('商议-至殿门', '商议，惇至殿门')

    # 郭汜
    text = text.replace('报知-亦大怒', '报知，汜亦大怒')

    # 曹操/刘备等代词
    text = text.replace('二人-曰：刘备', '二人，操曰：刘备')
    text = text.replace('不答-出，郭嘉', '不答，备出，郭嘉')
    text = text.replace('答-书曰：吾日', '答彧书曰：吾日')

    # 赵云
    text = text.replace('出马-骂曰', '出马，云骂曰')
    text = text.replace('见-在万军', '见云在万军')
    text = text.replace('拜受-辞去', '拜受，祎辞去')  # 费祎

    # 陈珪命陈登
    text = text.replace('其事-命登', '其事，珪命登')

    # 李傕问帝求食
    text = text.replace('问-取米', '问傕取米')
    text = text.replace('-怒曰：朝夕上饭', '傕怒曰：朝夕上饭')

    # 董承/太医
    text = text.replace('召-问其故-曰：主簿', '召惇问其故。惇曰：主簿')

    # 姜维受降
    text = text.replace('来见-拜伏', '来见，维拜伏')

    # 王平截击
    text = text.replace('后路-大叫', '后路，平大叫')

    # 曹丕篡汉相关
    text = text.replace('中-大惊昏倒', '中，帝大惊昏倒')

    # 全祎/全端书信
    text = text.replace('怿得-书', '怿得祎书')

    # 曹性射夏侯惇
    text = text.replace('而走-不舍', '而走，惇不舍')

    # 关兴追张郃
    text = text.replace('便走-随后', '便走，郃随后')
    text = text.replace('败走-奋怒', '败走，郃奋怒')
    text = text.replace('而走-又追赶', '而走，郃又追赶')

    # 耿纪韦晃见金祎
    text = text.replace('见-果有忠义', '见祎果有忠义')

    # 邓艾下床
    text = text.replace('下床来-叱', '下床来，瓘叱')

    # 陶濬兵溃
    text = text.replace('自去-得脱出', '自去，-得脱出')  # 保留，主语不明

    # 刘璝剩余
    text = text.replace('刘-曰', '刘璝曰')

    # === 8. 句中代词替换（最后处理） ===

    # 彭羕自荐
    text = text.replace('问-从何', '问羕从何')
    text = text.replace('而来-曰：吾特来', '而来，羕曰：吾特来')

    # 夏侯惇射猎荐典韦
    text = text.replace('山中-出', '山中，惇出')

    # 吕布冲阵，傕军不能当
    text = text.replace('过来-军', '过来，傕军')

    # 夏侯惇追高顺
    text = text.replace('阵来-纵马', '阵来，惇纵马')

    # 郭淮星夜来救
    text = text.replace('星夜来-城', '星夜来雍城')

    # 金祎宅二人至
    text = text.replace('二人至-具言', '二人至，祎具言')

    # 乐綝家
    text = text.replace('-慌上楼', '綝慌上楼')

    # 姜维问百姓
    text = text.replace('奔走-问', '奔走，维问')

    # 张郃追关兴
    text = text.replace('便走-随后', '便走，郃随后')

    # 曹操摆阵
    text = text.replace('忽起-便', '忽起，操便')

    # 张郃下马入帐
    text = text.replace('军到-下马', '军到，郃下马')

    # 刘禅辞诸葛
    text = text.replace('不受-曰：丞相', '不受，帝曰：丞相')

    # 曹操脱出
    text = text.replace('自去-得脱', '自去，操得脱')

    # 赵云兵少烧栈道
    text = text.replace('而去-因兵少', '而去，云因兵少')

    # 陈珪说吕布
    text = text.replace('以故-曰：此乃', '以故，珪曰：此乃')

    # 哨马叫
    text = text.replace('哨马-叫曰', '哨马叫曰')

    # 使者来结亲
    text = text.replace('特使-来', '特使某来')
    text = text.replace('使-手下', '使手下')

    # 兴苞赶来，惇走入城
    text = text.replace('赶来-走入', '赶来，惇走入')

    # 滚下床来，瓘叱
    text = text.replace('床来-叱', '床来，瓘叱')

    # === 9. 最后一批人名地名 ===

    # 郿坞（补充模式）
    for pat in ['筑-坞', '还-坞', '到-坞', '葬-坞']:
        text = text.replace(pat, pat.replace('-', '郿'))

    # 朱儁（讨黄巾主将，大量句中代词）
    jun_replacements = [
        '谓-曰：为社稷', '与-计曰', '与-各引', '山后-令玄德',
        '弃城而奔-与玄德', '与-交战', '宛城-离十里',
        '皆平-班师', '于地-归家', '计议-曰：彼用',
    ]
    for pat in jun_replacements:
        text = text.replace(pat, pat.replace('-', '儁'))

    # 李傕（句中代词）
    jue_replacements = [
        '居民-侄李暹', '左右-怒曰', '土色-谓帝曰',
        '渐涣-闻郦言', '出营-收拾车驾', '大司马-喜曰',
    ]
    for pat in jue_replacements:
        text = text.replace(pat, pat.replace('-', '傕'))

    # 张郃（截住去路）
    text = text.replace('去路-大怒', '去路，郃大怒')

    # 臧旻（汉末刺史）
    text = text.replace('臧-上表', '臧旻上表')

    # 封谞（补充）
    text = text.replace('况封-等', '况封谞等')

    # 董旻（董卓弟）
    text = text.replace('封弟董-为', '封弟董旻为')

    # 轘辕关
    text = text.replace('塞-辕', '塞轘辕')

    # 衠钢剑（貂蝉诗）
    text = text.replace('吐-钢剑', '吐衠钢剑')

    # 马日磾（补充）
    text = text.replace('日-无言', '日磾无言')

    # 陈珪（补充：告以故）
    text = text.replace('以故-曰', '以故，珪曰')

    # 曹操赏二人
    text = text.replace('二人-曰', '二人，操曰')

    # 杨彪谓朱儁
    text = text.replace('彪谓-曰', '彪谓儁曰')

    # 彭羕与刘备
    text = text.replace('其故-曰：将军', '其故，羕曰：将军')

    # 朱儁计议
    text = text.replace('计议-曰', '计议，儁曰')

    # 陈珪
    text = text.replace('陈-曰：不可', '陈珪曰：不可')
    text = text.replace('陈-何在', '陈珪何在')

    # 荀彧
    text = text.replace('操答-书曰', '操答彧书曰')
    text = text.replace('操以是告-曰', '操以是告彧曰')
    text = text.replace('用兵-有一计', '用兵，彧有一计')

    # 夏侯惇
    text = text.replace('迎之-乃与曹洪', '迎之，惇乃与曹洪')
    text = text.replace('左目-大叫', '左目，惇大叫')

    # 入郿坞
    text = text.replace('入-坞', '入郿坞')

    # 于贼阵中
    text = text.replace('于-阵中', '于贼阵中')

    # 饱则飏去（养鹰之喻）
    text = text.replace('饱则-去', '饱则飏去')

    # 秋狝冬狩（古礼）
    text = text.replace('秋-冬狩', '秋狝冬狩')

    return text


def process_file(filepath: Path):
    """处理单个文件"""
    text = filepath.read_text(encoding='utf-8', errors='replace')
    original_len = len(text)
    fixed = fix_text(text)

    # 统计修正
    dash_count_before = text.count('-')
    dash_count_after = fixed.count('-')
    zao_before = len(re.findall(r'(?<![急浮焦暴少])躁(?!动)', text))
    zao_after = len(re.findall(r'(?<![急浮焦暴少])躁(?!动)', fixed))

    filepath.write_text(fixed, encoding='utf-8')
    print(f"[+] {filepath.name}")
    print(f"    躁→操: {zao_before - zao_after} 处")
    print(f"    -→生僻字: {dash_count_before - dash_count_after} 处")
    print(f"    文件大小: {original_len} → {len(fixed)} 字符")


def main():
    if len(sys.argv) < 2:
        print("用法: python fix_text.py <txt文件或目录>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if target.is_file():
        process_file(target)
    elif target.is_dir():
        txt_files = list(target.glob('*.txt'))
        print(f"[*] 发现 {len(txt_files)} 个 TXT 文件")
        for f in txt_files:
            process_file(f)
    else:
        print(f"[!] 路径不存在: {target}")
        sys.exit(1)


if __name__ == '__main__':
    main()
