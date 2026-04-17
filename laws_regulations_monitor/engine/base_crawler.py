"""
爬虫基类
定义统一的爬虫接口规范

所有具体爬虫必须继承 BaseCrawler 并实现 crawl() 方法。
引擎通过统一的接口调用，不关心具体实现。
"""

import logging
import time
import re
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urljoin, urlparse
import urllib.request
import urllib.error

logger = logging.getLogger('engine.base')


class BaseCrawler(ABC):
    """
    爬虫抽象基类

    设计原则：
    - 引擎不认识任何层级，只认配置
    - 所有爬虫共享相同接口，配置驱动行为
    - 子类只需实现 crawl()，其余能力由基类提供
    """

    # 类级别的爬虫注册表（method name -> class）
    _registry: Dict[str, type] = {}

    def __init_subclass__(cls, **kwargs):
        """自动注册实现了 crawl() 的爬虫子类"""
        super().__init_subclass__(**kwargs)
        # 注册时用类名去掉 Crawler 后缀作为 method 名
        method_name = cls.__name__.replace('Crawler', '').lower()
        if method_name and not method_name.startswith('_'):
            cls._registry[method_name] = cls

    def __init__(self, config: Dict[str, Any], **kwargs):
        """
        Args:
            config: 数据源配置字典，包含 url/method/headers 等
            **kwargs: 运行时参数，如 lookback_days, keywords
        """
        self.config = config
        self.lookback_days = kwargs.get('lookback_days', config.get('lookback_days', 730))
        self.keywords = kwargs.get('keywords', config.get('keywords', []))
        self.name = config.get('name', self.__class__.__name__)

        # 默认请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        extra_headers = config.get('headers', {})
        if isinstance(extra_headers, dict):
            self.headers.update(extra_headers)

        # 速率限制
        self.rate_limit = config.get('rate_limit', 1.0)
        self.timeout = config.get('timeout', 15)
        self.retry = config.get('retry', 3)

        # 已发现 URL 去重
        self._seen_urls: Set[str] = set()

    # ─── HTTP 请求 ────────────────────────────────────────────

    def fetch(self, url: str, encoding: str = 'utf-8') -> Optional[str]:
        """发起 HTTP GET 请求，自动重试"""
        for attempt in range(self.retry):
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    content_type = resp.headers.get('Content-Type', '')

                    # 非 HTML 内容（可能是文件）直接返回二进制
                    if 'html' not in content_type and 'text' not in content_type:
                        return resp.read()

                    # 探测真实编码
                    detected = encoding
                    for ct in content_type.split(';'):
                        if 'charset' in ct:
                            detected = ct.split('=')[-1].strip()
                            break

                    return resp.read().decode(detected, errors='replace')

            except urllib.error.HTTPError as e:
                logger.warning(f"  HTTP {e.code} [{url[:60]}]: {e.reason}")
                if e.code == 404:
                    return None
            except urllib.error.URLError as e:
                logger.warning(f"  URL错误 [{url[:60]}]: {e.reason}")
            except Exception as e:
                logger.error(f"  请求异常 [{url[:60]}]: {e}")

            if attempt < self.retry - 1:
                time.sleep(1)
        return None

    def _rate_limit(self) -> None:
        """速率限制"""
        time.sleep(self.rate_limit)

    # ─── URL 处理 ─────────────────────────────────────────────

    @staticmethod
    def normalize_url(url: str, base: str = '') -> str:
        """标准化 URL"""
        if not url or url.startswith('javascript:') or url.startswith('#'):
            return ''
        if base:
            return urljoin(base, url)
        return url

    @staticmethod
    def url_hash(url: str) -> str:
        """URL 哈希（去重用）"""
        return hashlib.md5(url.encode()).hexdigest()[:12]

    # ─── 日期处理 ─────────────────────────────────────────────

    def is_recent(self, date_str: str) -> bool:
        """检查日期是否在回查范围内"""
        if not date_str:
            return True  # 无法判断时默认通过

        formats = [
            '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d',
            '%Y年%m月%d日', '%Y年%m月%d日',
        ]
        date_str = date_str.strip()
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                cutoff = datetime.now() - timedelta(days=self.lookback_days)
                return dt >= cutoff
            except ValueError:
                continue
        return True  # 无法解析时默认通过

    @staticmethod
    def extract_date(text: str) -> Optional[str]:
        """从文本中提取日期"""
        patterns = [
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'(\d{4}/\d{1,2}/\d{1,2})',
            r'(\d{4}\.\d{1,2}\.\d{1,2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    # ─── 通用解析 ─────────────────────────────────────────────

    @staticmethod
    def extract_doc_number(text: str) -> Optional[str]:
        """提取文号"""
        patterns = [
            r'([^\s]{2,6}令第?\d+号)',
            r'([^\s]{2,6}〔\d{4}〕\d+号)',
            r'(国发〔\d{4}〕\d+号)',
            r'(国办发〔\d{4}〕\d+号)',
            r'(银保监发〔\d{4}〕\d+号)',
            r'(证监发〔\d{4}〕\d+号)',
            r'(工信部规〔\d{4}〕\d+号)',
            r'(公告第?\d+号)',
            r'[（\(〔【]\d{4}年?第?\d+号[）\〕】]',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def infer_author(url: str) -> str:
        """从 URL 推断发文机关"""
        domain = urlparse(url).netloc.lower()
        author_map = {
            'npc.gov.cn': '全国人大常委会',
            'flk.npc.gov.cn': '全国人大常委会',
            'gov.cn': '国务院',
            'moj.gov.cn': '司法部',
            'cac.gov.cn': '国家互联网信息办公室',
            'miit.gov.cn': '工业和信息化部',
            'mps.gov.cn': '公安部',
            'pbc.gov.cn': '中国人民银行',
            'cbirc.gov.cn': '国家金融监督管理总局',
            'csrc.gov.cn': '中国证券监督管理委员会',
            'nhc.gov.cn': '国家卫生健康委员会',
            'moe.gov.cn': '教育部',
            'mot.gov.cn': '交通运输部',
            'samr.gov.cn': '国家市场监督管理总局',
            'openstd.samr.gov.cn': '国家市场监督管理总局',
        }
        for dk, author in author_map.items():
            if dk in domain:
                return author
        return ''

    @staticmethod
    def infer_status(title: str) -> str:
        """推断法规状态"""
        if any(k in title for k in ['征求意见', '(征求意见稿)', '（征求意见稿）', '草案']):
            return '征求意见稿'
        return '现行有效'

    def matches_keywords(self, text: str) -> bool:
        """检查文本是否包含关键词（用于过滤）"""
        if not self.keywords:
            return True
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.keywords)

    # ─── 去重 ─────────────────────────────────────────────────

    def deduplicate(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """基于 title+date 去重"""
        seen = set()
        unique = []
        for item in items:
            key = (item.get('title', ''), item.get('date', ''))
            if key not in seen and key[0]:
                seen.add(key)
                unique.append(item)
        return unique

    # ─── 抽象接口 ─────────────────────────────────────────────

    @abstractmethod
    def crawl(self, config: Dict, **kwargs) -> List[Dict[str, Any]]:
        """
        执行爬取（子类必须实现）

        Args:
            config: 数据源配置字典
            **kwargs: 运行时参数（lookback_days, keywords 等）

        Returns:
            爬取结果列表，每项包含:
            {
                'title': str,       # 法规标题
                'url': str,         # 原文链接
                'date': str,        # 发布日期 (YYYY-MM-DD)
                'level': str,       # L1-L7 / EDB / REF
                'type': str,        # 法律/行政法规/部门规章等
                'author': str,      # 发文机关
                'doc_number': str, # 文号
                'status': str,     # 现行有效/征求意见稿
                'source': str,     # 来源名称
                'source_id': str,  # 来源ID
            }
        """
        pass

    # ─── 便捷方法 ─────────────────────────────────────────────

    def crawl_all(self) -> List[Dict[str, Any]]:
        """爬取所有（供直接调用的简便入口）"""
        try:
            results = self.crawl(self.config)
            logger.info(f"[{self.name}] 爬取完成: {len(results)} 条")
            return results
        except Exception as e:
            logger.error(f"[{self.name}] 爬取出错: {e}")
            return []
