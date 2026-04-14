"""
爬虫基类
定义统一的爬虫接口
"""

import logging
import time
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """爬虫基类"""

    def __init__(self, config: Dict[str, Any], lookback_days: int = 30):
        self.config = config
        self.lookback_days = lookback_days
        self.name = self.__class__.__name__.replace('Crawler', '')
        
        # 请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        # 已发现的 URL（去重）
        self._seen_urls: Set[str] = set()
        
        # 速率限制
        self.request_delay = config.get('request_delay', 2.0)  # 秒

    def _make_request(self, url: str, encoding: str = 'utf-8', 
                      timeout: int = 30) -> Optional[str]:
        """发起 HTTP 请求"""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # 检查是否重定向到文件
                content_type = resp.headers.get('Content-Type', '')
                
                if 'html' not in content_type and 'text' not in content_type:
                    # 可能是文件，直接返回二进制
                    return resp.read()
                
                charset = encoding
                for ct in resp.headers.get('Content-Type', '').split(';'):
                    if 'charset' in ct:
                        charset = ct.split('=')[-1].strip()
                
                return resp.read().decode(charset, errors='replace')
        
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP {e.code} [{url}]: {e.reason}")
            return None
        except urllib.error.URLError as e:
            logger.warning(f"URL 错误 [{url}]: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"请求异常 [{url}]: {e}")
            return None

    def _rate_limit(self) -> None:
        """速率限制"""
        time.sleep(self.request_delay)

    def _normalize_url(self, url: str, base: str = '') -> str:
        """标准化 URL"""
        if not url or url.startswith('javascript:') or url.startswith('#'):
            return ''
        if base:
            return urljoin(base, url)
        return url

    def _url_hash(self, url: str) -> str:
        """生成 URL 哈希（用于去重标识）"""
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _is_recent(self, date_str: str) -> bool:
        """
        检查日期是否在回查范围内
        
        Args:
            date_str: 日期字符串，格式如 2024-01-15, 2024年1月15日
        """
        if not date_str:
            return True  # 无法判断时默认通过
        
        # 尝试多种日期格式
        date_formats = [
            '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d',
            '%Y年%m月%d日', '%Y年%m月%d日',
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                cutoff = datetime.now() - timedelta(days=self.lookback_days)
                return dt >= cutoff
            except ValueError:
                continue
        
        # 无法解析日期
        return True

    def _extract_date(self, text: str) -> Optional[str]:
        """从文本中提取日期"""
        import re
        patterns = [
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'(\d{4}/\d{1,2}/\d{1,2})',
            r'(\d{4}\.\d{1,2}\.\d{1,2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4})\.(\d{1,2})\.(\d{1,2})',
        ]
        
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        return None

    @abstractmethod
    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """
        执行爬取
        
        Returns:
            爬取结果列表，每项包含:
            {
                'title': str,       # 法规标题
                'url': str,         # 原文链接
                'date': str,        # 发布日期
                'level': str,       # L1-L7 或 case
                'type': str,        # 法律/行政法规/部门规章等
                'author': str,      # 发文机关
                'doc_number': str,  # 文号
                'summary': str,    # 摘要（可选）
                'download_url': str, # PDF等文件下载地址（可选）
                'status': str,     # 状态
            }
        """
        pass

    def crawl_all(self) -> List[Dict[str, Any]]:
        """爬取所有数据源"""
        results = []
        try:
            results = self.crawl()
            logger.info(f"[{self.name}] 爬取完成: {len(results)} 条")
        except Exception as e:
            logger.error(f"[{self.name}] 爬取出错: {e}")
        return results

    def _deduplicate(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """基于 URL 去重"""
        seen = set()
        unique = []
        
        for item in items:
            url = item.get('url', '')
            if url and url not in seen:
                seen.add(url)
                unique.append(item)
        
        return unique

    def _extract_doc_number(self, text: str) -> Optional[str]:
        """从文本中提取文号"""
        import re
        # 常见文号格式: 公安部令第XX号, 国令第XXX号, 工信部规〔2024〕X号
        patterns = [
            r'([^\s]{2,6}令第?\d+号)',
            r'([^\s]{2,6}〔\d{4}〕\d+号)',
            r'(国发〔\d{4}〕\d+号)',
            r'(国办发〔\d{4}〕\d+号)',
            r'(银保监发〔\d{4}〕\d+号)',
            r'(证监发〔\d{4}〕\d+号)',
            r'(工信部规〔\d{4}〕\d+号)',
            r'(公告第?\d+号)',
        ]
        
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
        return None

    def _filter_by_keywords(self, text: str, keywords: List[str]) -> bool:
        """检查文本是否包含任意关键词"""
        if not keywords:
            return True
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def _extract_author_from_url(self, url: str) -> str:
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
            'gzw.gov.cn': '广东省人民政府',
            'beijing.gov.cn': '北京市人民政府',
            'shanghai.gov.cn': '上海市人民政府',
        }
        
        for domain_key, author in author_map.items():
            if domain_key in domain:
                return author
        return ''
