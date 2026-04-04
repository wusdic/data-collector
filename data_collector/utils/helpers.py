"""
通用工具函数
"""

import re
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin


def normalize_text(text: str) -> str:
    """归一化文本"""
    if not text:
        return ''
    
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text)
    
    # 移除特殊字符（保留中文、英文、数字、常用标点）
    text = re.sub(r'[^\w\u4e00-\u9fa5\s.,;:!?，。；：！？、]', '', text)
    
    return text.strip()


def extract_keywords(text: str, min_length: int = 2, max_keywords: int = 10) -> List[str]:
    """
    从文本提取关键词
    
    Args:
        text: 文本
        min_length: 最小词长度
        max_keywords: 最大关键词数
        
    Returns:
        关键词列表
    """
    if not text:
        return []
    
    # 简单分词（基于标点和空格）
    words = re.findall(r'[\u4e00-\u9fa5]{2,}|[\w]{3,}', text)
    
    # 统计词频
    word_freq = {}
    for word in words:
        word_lower = word.lower()
        word_freq[word_lower] = word_freq.get(word_lower, 0) + 1
    
    # 按频率排序
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    
    # 返回 top N
    return [w[0] for w in sorted_words[:max_keywords]]


def extract_domain(url: str) -> str:
    """提取域名"""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return ''


def is_valid_url(url: str) -> bool:
    """验证 URL 是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def generate_id(text: str = '') -> str:
    """生成唯一 ID"""
    import uuid
    unique = f"{uuid.uuid4()}{text}{datetime.now().isoformat()}"
    return hashlib.md5(unique.encode()).hexdigest()[:12]


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"


def parse_date(date_str: str) -> Optional[datetime]:
    """解析日期字符串"""
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%Y%m%d',
        '%d/%m/%Y',
        '%m/%d/%Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def safe_get(dictionary: Dict, *keys, default=None) -> Any:
    """安全获取嵌套字典值"""
    result = dictionary
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default
    return result


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """分块列表"""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def merge_dicts(*dicts: Dict) -> Dict:
    """合并字典"""
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result
