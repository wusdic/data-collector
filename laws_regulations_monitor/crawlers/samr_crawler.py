"""
国家标准全文公开系统爬虫
https://openstd.samr.gov.cn/
来源: L4-国家标准
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from .base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class SAMRCrawler(BaseCrawler):
    """国家标准全文公开系统爬虫"""

    def __init__(self, config: Dict[str, Any], lookback_days: int = 30):
        super().__init__(config, lookback_days)
        self.base_url = config.get('base_url', 'https://openstd.samr.gov.cn/')
        self.search_url = config.get('search_url', 'https://openstd.samr.gov.cn/bzgk/gb/')

    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """
        爬取国家标准
        
        标准分为:
        - GB: 国家标准 (强制/推荐)
        - GB/T: 推荐性国家标准
        """
        results = []
        
        # 爬取最新发布的国家标准
        latest = self._crawl_latest_standards()
        for std in latest:
            std['level'] = 'L4'
            std['type'] = '国家标准'
            std['author'] = '国家市场监督管理总局'
        results.extend(latest)
        
        # 爬取最近更新的标准
        updated = self._crawl_updated_standards()
        for std in updated:
            std['level'] = 'L4'
            std['type'] = '国家标准'
            std['author'] = '国家市场监督管理总局'
        results.extend(updated)
        
        return self._deduplicate(results)

    def _crawl_latest_standards(self) -> List[Dict[str, Any]]:
        """爬取最新发布的标准"""
        results = []
        
        # SAMR 标准检索页面
        urls = [
            f"{self.search_url}?type=standard&sort=1&page=1",  # 最新发布
        ]
        
        for url in urls:
            try:
                content = self._make_request(url)
                if content:
                    items = self._parse_standard_list(content, url)
                    results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"SAMR 标准列表爬取失败 [{url}]: {e}")
        
        return results

    def _crawl_updated_standards(self) -> List[Dict[str, Any]]:
        """爬取最近更新的标准"""
        return self._crawl_latest_standards()  # 复用

    def _parse_standard_list(self, html: str, base_url: str) -> List[Dict[str, Any]]:
        """解析标准列表页"""
        results = []
        
        # SAMR 标准列表常见的 HTML 结构
        # 提取标准号和标题
        patterns = [
            # <a href="/std/show?idd=xxx">GB/T 12345-2023</a> ...
            r'<a[^>]+href="(/std/show\?[^"]+)"[^>]*>([^<]+GB/T?\s*[\d\-\:]+[^<]*)</a>',
            # 标准列表项
            r'(GB/T?\s*[\d\.\-]+)[^<]*<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
        ]
        
        seen = set()
        
        for pattern in patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for m in matches:
                if len(m.groups()) >= 3:
                    std_num = m.group(1).strip()
                    url = m.group(2) if len(m.groups()) >= 2 else m.group(1)
                    title = m.group(3).strip() if len(m.groups()) >= 3 else std_num
                else:
                    url = m.group(1)
                    std_num = m.group(2).strip() if len(m.groups()) >= 2 else ''
                    title = std_num
                
                if not title:
                    continue
                
                key = f"{std_num}:{title}"
                if key in seen:
                    continue
                seen.add(key)
                
                full_url = f"{self.base_url.rstrip('/')}{url}" if url.startswith('/') else url
                
                # 从标题或上下文提取日期
                date = self._extract_date_from_context(html, title)
                
                results.append({
                    'title': title,
                    'url': full_url,
                    'date': date or '',
                    'doc_number': std_num,
                    'author': '国家市场监督管理总局',
                    'summary': '',
                    'download_url': '',
                    'status': '现行有效',
                })
        
        return results

    def _extract_date_from_context(self, html: str, keyword: str) -> Optional[str]:
        """从 HTML 上下文中提取日期"""
        idx = html.find(keyword)
        if idx == -1:
            return None
        
        # 查找关键词附近的日期
        snippet = html[max(0, idx-200):idx+200]
        return self._extract_date(snippet)

    def get_standard_detail(self, std_id: str) -> Optional[Dict[str, Any]]:
        """
        获取标准详细信息
        
        Args:
            std_id: 标准 ID 或 URL
        """
        if not std_id.startswith('http'):
            std_id = f"{self.base_url}std/show?idd={std_id}"
        
        content = self._make_request(std_id)
        if not content:
            return None
        
        detail = {
            'url': std_id,
            'title': '',
            'doc_number': '',
            'author': '国家市场监督管理总局',
            'publish_date': '',
            'effective_date': '',
            'status': '现行有效',
            'download_url': '',
            'summary': '',
        }
        
        # 提取标题
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if title_m:
            detail['title'] = title_m.group(1).strip()
        
        # 提取标准号
        std_num_m = re.search(r'(GB/T?\s*[\d\.\-]+)', content)
        if std_num_m:
            detail['doc_number'] = std_num_m.group(1)
        
        # 提取发布日期
        date_m = re.search(r'发布日期[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', content)
        if date_m:
            detail['publish_date'] = date_m.group(1)
        
        # 提取实施日期
        eff_m = re.search(r'实施日期[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})', content)
        if eff_m:
            detail['effective_date'] = eff_m.group(1)
        
        # 提取 PDF 链接
        pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', content)
        if pdf_m:
            detail['download_url'] = pdf_m.group(1)
        
        # 提取摘要
        summary_m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', content)
        if summary_m:
            detail['summary'] = summary_m.group(1)
        
        return detail
