"""
义务条款提取引擎
从法规文本中提取义务条款，并分类：
- must: "应当"、"必须" → 橙色
- must_not: "不得"、"禁止" → 红色
- may: "可以"、"有权" → 蓝色
- punishment: 处罚依据 → 紫色
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Obligation:
    """义务条款"""
    regulation_id: str  # 法规标识
    article_number: str  # 条款编号
    obligation_type: str  # must / must_not / may / punishment
    content: str  # 义务内容
    keywords: List[str]  # 关键词
    applicability: dict  # 适用性信息 {industries, scale, data_types, regions}


# 义务类型模式定义
OBLIGATION_PATTERNS = {
    'must': [
        r'应当\s*(.+?)(?=[，。；]|$)',
        r'必须\s*(.+?)(?=[，。；]|$)',
        r'应当\s*(.+?)\s*[，。；]',
    ],
    'must_not': [
        r'不得\s*(.+?)(?=[，。；]|$)',
        r'禁止\s*(.+?)(?=[，。；]|$)',
        r'严禁\s*(.+?)(?=[，。；]|$)',
        r'不允许\s*(.+?)(?=[，。；]|$)',
    ],
    'may': [
        r'可以\s*(.+?)(?=[，。；]|$)',
        r'有权\s*(.+?)(?=[，。；]|$)',
        r'有权\s*(.+?)\s*[，。；]',
    ],
    'punishment': [
        r'处\s*\d+[万千百]?(?:元|罚款)',
        r'罚款\s*\d+',
        r'警告\s*[，；]',
        r'责令\s*(?:改正|停产|停业)',
        r'没收\s*(?:违法|所得)',
        r'情节严重.*?处罚',
        r'依法追究.*?责任',
    ],
}


# 适用行业关键词
INDUSTRY_KEYWORDS = {
    '互联网': ['互联网', '网络', '信息服务', '平台'],
    '金融': ['金融', '银行', '证券', '保险', '支付'],
    '医疗': ['医疗', '医药', '健康', '医院'],
    '教育': ['教育', '学校', '培训', '在线教育'],
    '电商': ['电商', '网络交易', '平台'],
    '数据处理': ['数据处理', '大数据', '云计算'],
    '个人信息处理': ['个人信息', '个人隐私'],
}


# 规模关键词
SCALE_KEYWORDS = {
    '大型': ['大型', '重要', '关键信息基础设施', '重要领域'],
    '中型': ['中型', '一定规模'],
    '小型': ['小型', '微小'],
    '所有': ['所有', '任何', '一律'],
}


# 数据类型关键词
DATA_TYPE_KEYWORDS = {
    '个人信息': ['个人信息', '个人隐私', '个人数据'],
    '重要数据': ['重要数据', '核心数据', '国家数据'],
    '商业秘密': ['商业秘密', '机密'],
    '一般数据': ['数据', '信息'],
}


def classify_obligation_type(sentence: str) -> str:
    """判断义务类型"""
    if not sentence:
        return "unknown"
    
    # 优先检查处罚类型
    for pattern in OBLIGATION_PATTERNS['punishment']:
        if re.search(pattern, sentence):
            return "punishment"
    
    # 检查"不得/禁止"
    for pattern in OBLIGATION_PATTERNS['must_not']:
        if re.search(pattern, sentence):
            return "must_not"
    
    # 检查"应当/必须"
    for pattern in OBLIGATION_PATTERNS['must']:
        if re.search(pattern, sentence):
            return "must"
    
    # 检查"可以/有权"
    for pattern in OBLIGATION_PATTERNS['may']:
        if re.search(pattern, sentence):
            return "may"
    
    return "unknown"


def extract_article_number(text: str) -> str:
    """提取条款编号"""
    if not text:
        return ""
    
    patterns = [
        r'第[一二三四五六七八九十百零\d]+条',
        r'第\s*\d+\s*条',
        r'^\s*\d+\.',
        r'^\s*\d+\s*、',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    
    return ""


def extract_applicability(text: str) -> dict:
    """提取适用性信息"""
    applicability = {
        'industries': [],
        'scale': [],
        'data_types': [],
        'regions': [],
    }
    
    if not text:
        return applicability
    
    # 提取行业
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            if industry not in applicability['industries']:
                applicability['industries'].append(industry)
    
    # 提取规模
    for scale, keywords in SCALE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            if scale not in applicability['scale']:
                applicability['scale'].append(scale)
    
    # 提取数据类型
    for dtype, keywords in DATA_TYPE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            if dtype not in applicability['data_types']:
                applicability['data_types'].append(dtype)
    
    # 提取地区（简单模式）
    region_patterns = [
        r'(?:在|向)(.+?)(?:地区|省|市|自治区)',
        r'(?:北京|上海|广东|浙江|江苏)',
    ]
    for pattern in region_patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            if m not in applicability['regions']:
                applicability['regions'].append(m)
    
    return applicability


def _split_into_sentences(text: str) -> List[str]:
    """将文本分割为句子"""
    if not text:
        return []
    
    # 按中文字号、句号、问号分割
    sentences = re.split(r'[；。；\n]+', text)
    return [s.strip() for s in sentences if s.strip()]


def extract_obligations(text: str, regulation_id: str) -> List[Obligation]:
    """
    从文本中提取所有义务条款
    
    Args:
        text: 法规文本内容
        regulation_id: 法规标识
    
    Returns:
        List[Obligation]
    """
    if not text:
        return []
    
    obligations = []
    sentences = _split_into_sentences(text)
    
    for sentence in sentences:
        if not sentence or len(sentence) < 5:
            continue
        
        # 判断义务类型
        ob_type = classify_obligation_type(sentence)
        
        if ob_type == "unknown":
            continue
        
        # 提取条款编号
        article_num = extract_article_number(sentence)
        
        # 提取关键词
        keywords = []
        for kw in ['应当', '必须', '不得', '禁止', '可以', '有权', '处罚']:
            if kw in sentence:
                keywords.append(kw)
        
        # 提取适用性
        applicability = extract_applicability(sentence)
        
        obligation = Obligation(
            regulation_id=regulation_id,
            article_number=article_num,
            obligation_type=ob_type,
            content=sentence[:200],  # 限制长度
            keywords=keywords,
            applicability=applicability
        )
        
        obligations.append(obligation)
    
    return obligations


if __name__ == "__main__":
    # 简单测试
    test_text = """
    网络运营者应当按照网络安全等级保护制度的要求，履行下列安全保护义务：
    （一）制定内部安全管理制度和操作规程，确定网络安全负责人，落实网络安全保护责任；
    （二）采取防范计算机病毒和网络攻击、网络侵入等危害网络安全行为的技术措施；
    （三）采取监测、记录网络运行状态、网络安全事件的技术措施，并按照规定留存相关网络日志不少于六个月；
    （四）采取数据分类、重要数据备份和加密等措施；
    （五）法律、行政法规规定的其他义务。
    违反本法第二十一条规定，有下列行为之一的，由有关主管部门责令改正，给予警告；
    拒不改正或者导致危害网络安全后果的，处一万元以上十万元以下罚款。
    """
    
    obligations = extract_obligations(test_text, "网络安全法_第21条")
    print(f"提取到 {len(obligations)} 条义务条款:")
    for ob in obligations:
        print(f"  [{ob.obligation_type}] {ob.content[:50]}...")
        print(f"    适用性: {ob.applicability}")