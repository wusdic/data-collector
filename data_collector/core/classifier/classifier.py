"""
资料分类器
支持基于规则的自动分类、关键词提取、标签生成
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from collections import Counter
import hashlib

logger = logging.getLogger(__name__)


class Category:
    """分类"""
    
    def __init__(self, name: str, keywords: List[str], extensions: Optional[List[str]] = None):
        self.name = name
        self.keywords = keywords
        self.extensions = extensions or []
        self._keyword_pattern = self._compile_pattern(keywords)
    
    @staticmethod
    def _compile_pattern(keywords: List[str]) -> re.Pattern:
        """编译关键词正则模式"""
        pattern = '|'.join(re.escape(kw) for kw in keywords)
        return re.compile(pattern, re.IGNORECASE)
    
    def match(self, text: str, extension: str = '') -> float:
        """
        计算匹配度
        
        Args:
            text: 文本内容
            extension: 文件扩展名
            
        Returns:
            匹配度分数 0-1
        """
        score = 0.0
        matches = self._keyword_pattern.findall(text)
        
        if matches:
            # 基础匹配分数
            score = min(len(matches) / 5, 1.0)
        
        # 扩展名加成
        if extension and extension.lower() in self.extensions:
            score = min(score + 0.2, 1.0)
        
        return score
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'keywords': self.keywords,
            'extensions': self.extensions,
        }


class AutoTag:
    """自动标签"""
    
    def __init__(self, keyword: str, tag: str):
        self.keyword = keyword
        self.tag = tag
        self.pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    
    def match(self, text: str) -> bool:
        """检查是否匹配"""
        return bool(self.pattern.search(text))
    
    def to_dict(self) -> Dict[str, str]:
        return {'keyword': self.keyword, 'tag': self.tag}


class Classifier:
    """
    资料分类器
    支持自动分类、标签生成、重复检测
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化分类器
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # 初始化分类
        self.categories: List[Category] = []
        self._init_categories()
        
        # 初始化自动标签
        self.auto_tags: List[AutoTag] = []
        self._init_auto_tags()
        
        # 已知内容指纹（用于去重）
        self.known_fingerprints: Set[str] = set()
    
    def _init_categories(self) -> None:
        """初始化分类"""
        categories_config = self.config.get('categories', [])
        
        for cat_config in categories_config:
            category = Category(
                name=cat_config['name'],
                keywords=cat_config.get('keywords', []),
                extensions=cat_config.get('extensions', [])
            )
            self.categories.append(category)
        
        logger.info(f"已加载 {len(self.categories)} 个分类")
    
    def _init_auto_tags(self) -> None:
        """初始化自动标签"""
        tags_config = self.config.get('auto_tags', [])
        
        for tag_config in tags_config:
            auto_tag = AutoTag(
                keyword=tag_config['keyword'],
                tag=tag_config['tag']
            )
            self.auto_tags.append(auto_tag)
        
        logger.info(f"已加载 {len(self.auto_tags)} 个自动标签规则")
    
    def classify(
        self,
        title: str,
        content: str = '',
        extension: str = '',
        url: str = ''
    ) -> Dict[str, Any]:
        """
        对资料进行分类
        
        Args:
            title: 标题
            content: 正文内容
            extension: 文件扩展名
            url: 来源URL
            
        Returns:
            分类结果
        """
        text = f"{title} {content} {url}"
        
        # 计算各类别匹配度
        category_scores = []
        for category in self.categories:
            score = category.match(text, extension)
            if score > 0:
                category_scores.append({
                    'category': category.name,
                    'score': round(score, 2),
                    'matched_keywords': self._get_matched_keywords(category, text)
                })
        
        # 按分数排序
        category_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # 生成标签
        tags = self.generate_tags(title, content)
        
        # 生成指纹
        fingerprint = self.generate_fingerprint(title, content)
        
        # 检查重复
        is_duplicate = fingerprint in self.known_fingerprints
        
        return {
            'primary_category': category_scores[0]['category'] if category_scores else '未分类',
            'categories': category_scores,
            'tags': tags,
            'fingerprint': fingerprint,
            'is_duplicate': is_duplicate,
        }
    
    def _get_matched_keywords(self, category: Category, text: str) -> List[str]:
        """获取匹配的关键词"""
        matches = category._keyword_pattern.findall(text)
        return list(set(matches))
    
    def generate_tags(self, title: str, content: str = '') -> List[str]:
        """
        生成标签
        
        Args:
            title: 标题
            content: 正文
            
        Returns:
            标签列表
        """
        text = f"{title} {content[:1000]}"  # 限制内容长度
        tags = set()
        
        for auto_tag in self.auto_tags:
            if auto_tag.match(text):
                tags.add(auto_tag.tag)
        
        # 从标题提取词组作为标签
        words = re.findall(r'[\u4e00-\u9fa5]{2,}[^\s]', title)
        tag_words = [w for w in words if len(w) >= 2][:3]
        tags.update(tag_words)
        
        return list(tags)
    
    def generate_fingerprint(self, title: str, content: str = '') -> str:
        """
        生成内容指纹（用于去重）
        
        Args:
            title: 标题
            content: 正文
            
        Returns:
            指纹字符串
        """
        # 归一化文本
        normalized = self._normalize_text(title + content)
        
        # 生成 MD5 指纹
        fingerprint = hashlib.md5(normalized.encode('utf-8')).hexdigest()
        
        return fingerprint
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """归一化文本"""
        # 转为小写
        text = text.lower()
        
        # 移除特殊字符
        text = re.sub(r'[^\w\u4e00-\u9fa5]', '', text)
        
        # 移除多余空格
        text = re.sub(r'\s+', '', text)
        
        return text
    
    def add_fingerprint(self, fingerprint: str) -> None:
        """添加已知指纹"""
        self.known_fingerprints.add(fingerprint)
    
    def add_category(self, name: str, keywords: List[str], extensions: Optional[List[str]] = None) -> None:
        """
        添加新分类
        
        Args:
            name: 分类名称
            keywords: 关键词列表
            extensions: 文件扩展名列表
        """
        category = Category(name, keywords, extensions)
        self.categories.append(category)
        logger.info(f"添加分类: {name}")
    
    def add_auto_tag(self, keyword: str, tag: str) -> None:
        """
        添加自动标签规则
        
        Args:
            keyword: 关键词
            tag: 标签名
        """
        auto_tag = AutoTag(keyword, tag)
        self.auto_tags.append(auto_tag)
        logger.info(f"添加自动标签: {keyword} -> {tag}")
    
    def list_categories(self) -> List[Dict[str, Any]]:
        """列出所有分类"""
        return [cat.to_dict() for cat in self.categories]
    
    def list_auto_tags(self) -> List[Dict[str, str]]:
        """列出所有自动标签规则"""
        return [tag.to_dict() for tag in self.auto_tags]
    
    def suggest_category(self, name: str) -> Optional[str]:
        """
        根据名称建议分类
        
        Args:
            name: 项目名称
            
        Returns:
            建议的分类名称
        """
        for category in self.categories:
            if category.match(name):
                return category.name
        
        return None
    
    def batch_classify(
        self,
        items: List[Dict[str, str]],
        title_field: str = 'title',
        content_field: str = 'content'
    ) -> List[Dict[str, Any]]:
        """
        批量分类
        
        Args:
            items: 项目列表
            title_field: 标题字段名
            content_field: 内容字段名
            
        Returns:
            分类结果列表
        """
        results = []
        
        for item in items:
            title = item.get(title_field, '')
            content = item.get(content_field, '')
            
            result = self.classify(title, content)
            results.append(result)
        
        return results
