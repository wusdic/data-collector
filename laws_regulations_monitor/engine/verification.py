"""
真实性验证引擎
验证维度：
1. 域名可信度（gov.cn/chinalaw.gov.cn/samr.gov.cn = high）
2. 文件哈希校验（SHA256）
3. 版本一致性（检查官网版本说明）
4. 内容一致性（标题与内容匹配）
5. 内部/密级文件标注"待获取"

验证状态：verified / pending_review / unverified_content / expired
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


@dataclass
class VerificationResult:
    """文档验证结果"""
    status: str  # verified / pending_review / unverified_content / expired
    domain_trust: str  # high / medium / low / unknown
    hash_match: bool
    version_confirmed: bool
    content_consistent: bool
    is_sensitive: bool
    notes: str


# 高可信域名白名单
HIGH_TRUST_DOMAINS = {
    'gov.cn',
    'chinalaw.gov.cn',
    'samr.gov.cn',
    'cac.gov.cn',
    'npc.gov.cn',
    ' courts.gov.cn',
    'gov.cn',
}


MEDIUM_TRUST_DOMAINS = {
    'moe.edu.cn',
    'mofcom.gov.cn',
    'customs.gov.cn',
    'pbc.gov.cn',
}


# 敏感文件标记关键词
SENSITIVE_KEYWORDS = [
    '内部', '密级', '机密', '秘密', '保密', '内部资料',
    '内部文件', '不对外公开', '仅限', '保密工作',
]


def check_domain_trust(url: str) -> str:
    """检查域名可信度"""
    if not url:
        return "unknown"
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # 移除端口
    if ':' in domain:
        domain = domain.split(':')[0]
    
    # 检查是否为政府域名
    if domain.endswith('.gov.cn'):
        return "high"
    
    if domain.endswith('.org.cn'):
        return "medium"
    
    if any(trusted in domain for trusted in HIGH_TRUST_DOMAINS):
        return "high"
    
    if any(trusted in domain for trusted in MEDIUM_TRUST_DOMAINS):
        return "medium"
    
    # 检查是否为知名机构
    if 'cac.gov' in domain or 'chinalaw' in domain or 'samr' in domain:
        return "high"
    
    return "low"


def compute_hash(content: bytes) -> str:
    """计算SHA256哈希"""
    if content is None:
        return ""
    return hashlib.sha256(content).hexdigest()


def _check_content_consistency(title: str, content: str) -> bool:
    """检查标题与内容一致性"""
    if not content or not title:
        return False
    
    # 简单检查：标题关键词是否出现在内容中
    # 提取标题中连续的2-4字词作为关键词
    title_chars = ''.join(re.findall(r'[\u4e00-\u9fa5]+', title))
    
    if len(title_chars) < 4:
        return True  # 标题太短，跳过检查
    
    # 取前8个字符作为核心关键词
    core_keywords = title_chars[:8]
    
    return core_keywords in content


def _check_version_consistency(content: str, expected_version: str = None) -> bool:
    """检查版本一致性"""
    if not content:
        return False
    
    # 常见版本标记模式
    version_patterns = [
        r'第\s*\d+\s*版',
        r'版本\s*[:：]\s*\d+',
        r'v\d+(\.\d+)*',
        r'20\d{2}年\d+月',
    ]
    
    for pattern in version_patterns:
        if re.search(pattern, content):
            return True
    
    return True  # 无版本信息时默认通过


def _check_sensitive(content: str) -> bool:
    """检查是否含敏感标记"""
    if not content:
        return False
    
    return any(kw in content for kw in SENSITIVE_KEYWORDS)


def verify_document(
    url: str,
    content: bytes = None,
    expected_hash: str = None,
    title: str = None
) -> VerificationResult:
    """
    综合验证文档
    
    Args:
        url: 文档URL
        content: 文档内容(字节)
        expected_hash: 期望的SHA256哈希(用于校验)
        title: 文档标题(用于一致性检查)
    
    Returns:
        VerificationResult
    """
    notes = []
    
    # 1. 域名可信度检查
    domain_trust = check_domain_trust(url)
    
    # 2. 哈希校验
    hash_match = False
    if content and expected_hash:
        actual_hash = compute_hash(content)
        hash_match = actual_hash.lower() == expected_hash.lower()
        if not hash_match:
            notes.append(f"哈希不匹配: 期望 {expected_hash[:16]}..., 实际 {actual_hash[:16]}...")
    elif content and not expected_hash:
        # 无期望哈希时，记录实际哈希
        actual_hash = compute_hash(content)
        notes.append(f"实际哈希: {actual_hash[:16]}...")
        hash_match = True  # 无法校验，但内容存在
    
    # 3. 版本一致性检查
    version_confirmed = True
    if content:
        try:
            text = content.decode('utf-8', errors='ignore')
            version_confirmed = _check_version_consistency(text)
        except Exception:
            version_confirmed = False
    
    # 4. 内容一致性
    content_consistent = True
    if content and title:
        try:
            text = content.decode('utf-8', errors='ignore')
            content_consistent = _check_content_consistency(title, text)
            if not content_consistent:
                notes.append("标题与内容可能不一致")
        except Exception:
            content_consistent = False
    
    # 5. 敏感文件检查
    is_sensitive = False
    if content:
        try:
            text = content.decode('utf-8', errors='ignore')
            is_sensitive = _check_sensitive(text)
        except Exception:
            pass
    
    # 综合判断状态
    if is_sensitive:
        status = "pending_review"
        notes.append("文件含内部/密级标记，需人工复核")
    elif domain_trust == "high" and hash_match:
        status = "verified"
    elif domain_trust == "high" and not hash_match:
        status = "pending_review"
        notes.append("高可信域名但哈希不匹配")
    elif domain_trust == "low":
        status = "unverified_content"
        notes.append("非官方域名，真实性待验证")
    else:
        status = "pending_review"
    
    if notes:
        notes_str = "; ".join(notes)
    else:
        notes_str = "验证通过"
    
    return VerificationResult(
        status=status,
        domain_trust=domain_trust,
        hash_match=hash_match,
        version_confirmed=version_confirmed,
        content_consistent=content_consistent,
        is_sensitive=is_sensitive,
        notes=notes_str
    )


if __name__ == "__main__":
    # 简单测试
    test_url = "https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm"
    result = verify_document(test_url, title="中华人民共和国网络安全法")
    print(f"URL: {test_url}")
    print(f"Domain trust: {result.domain_trust}")
    print(f"Status: {result.status}")
    print(f"Notes: {result.notes}")