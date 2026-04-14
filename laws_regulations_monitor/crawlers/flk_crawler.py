"""
国家法律法规数据库爬虫
https://flk.npc.gov.cn/
来源: L1-国家法律, L2-行政法规
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

from .base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class FLKCrawler(BaseCrawler):
    """国家法律法规数据库爬虫"""

    def __init__(self, config: Dict[str, Any], lookback_days: int = 30):
        super().__init__(config, lookback_days)
        self.base_url = config.get('base_url', 'https://flk.npc.gov.cn/')
        self.api_url = config.get('search_url', 'https://flk.npc.gov.cn/api/')

    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """
        爬取国家法律法规数据库
        
        FLK API 示例:
        https://flk.npc.gov.cn/api/v2/search?size=20&sort=1&page=1&type=&level=
        
        level 参数:
        - 1: 国家法律
        - 2: 行政法规
        - 3: 地方性法规
        - 4: 司法解释
        """
        results = []
        
        # L1: 国家法律
        laws = self._search_laws(level='1', page_size=50)
        for law in laws:
            law['level'] = 'L1'
            law['type'] = '法律'
        results.extend(laws)
        
        # L2: 行政法规
        regulations = self._search_regulations(level='2', page_size=50)
        for reg in regulations:
            reg['level'] = 'L2'
            reg['type'] = '行政法规'
        results.extend(regulations)
        
        return self._deduplicate(results)

    def _search_laws(self, level: str, page_size: int = 50) -> List[Dict[str, Any]]:
        """搜索国家法律"""
        results = []
        
        # 尝试使用 FLK API
        for page in range(1, 5):  # 最多4页
            try:
                items = self._fetch_api(level, page, page_size)
                if not items:
                    break
                results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"FLK API 请求失败 (level={level}, page={page}): {e}")
                break
        
        # 如果 API 失败，尝试网页爬取
        if not results:
            results = self._search_web(level)
        
        return results

    def _search_regulations(self, level: str, page_size: int = 50) -> List[Dict[str, Any]]:
        """搜索行政法规"""
        return self._search_laws(level, page_size)  # 复用同一方法

    def _fetch_api(self, level: str, page: int, page_size: int) -> List[Dict[str, Any]]:
        """调用 FLK 搜索 API"""
        try:
            # FLK 开放 API
            params = {
                'size': page_size,
                'sort': 1,  # 按发布时间排序
                'page': page,
                'level': level,
            }
            
            url = f"{self.api_url}search?{urlencode(params)}"
            content = self._make_request(url)
            
            if not content:
                return []
            
            data = json.loads(content)
            
            # FLK API 返回格式
            items = []
            if isinstance(data, dict):
                result_list = data.get('result', []) or data.get('data', []) or []
                for item in result_list:
                    items.append(self._parse_api_item(item))
            elif isinstance(data, list):
                for item in data:
                    items.append(self._parse_api_item(item))
            
            return items
        
        except json.JSONDecodeError as e:
            logger.warning(f"FLK JSON 解析失败: {e}")
            return []
        except Exception as e:
            logger.warning(f"FLK API 出错: {e}")
            return []

    def _parse_api_item(self, item: Dict) -> Dict[str, Any]:
        """解析 FLK API 单条记录"""
        # FLK 可能的字段名
        title = (
            item.get('law_name') or 
            item.get('title') or 
            item.get('name') or 
            item.get('lawTitle') or ''
        )
        
        url = (
            item.get('url') or 
            item.get('link') or 
            item.get('pdfUrl') or 
            item.get('file_url') or
            f"https://flk.npc.gov.cn/detail/{item.get('_id', item.get('id', ''))}" or ''
        )
        
        date = (
            item.get('publish_date') or 
            item.get('date') or 
            item.get('pubDate') or
            item.get('effect_date') or ''
        )
        
        author = (
            item.get('author') or 
            item.get('org') or 
            item.get('department') or 
            item.get('publishOrg') or '全国人民代表大会'
        )
        
        doc_number = (
            item.get('doc_number') or 
            item.get('documentNumber') or 
            item.get('code') or ''
        )
        
        return {
            'title': title,
            'url': url,
            'date': date,
            'author': author,
            'doc_number': doc_number,
            'level': item.get('level', ''),
            'type': item.get('type', ''),
            'summary': item.get('summary', item.get('description', '')),
            'download_url': item.get('pdfUrl') or item.get('file_url', ''),
            'status': '现行有效',
        }

    def _search_web(self, level: str) -> List[Dict[str, Any]]:
        """网页方式搜索（备用）"""
        results = []
        
        # FLK 首页最新法规列表
        urls_to_check = [
            f"{self.base_url}detail2?type=laws&level={level}",
            f"{self.base_url}detail2?type=laws",
        ]
        
        for url in urls_to_check:
            try:
                content = self._make_request(url)
                if content:
                    items = self._parse_html(content, url)
                    results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"FLK 网页爬取失败 [{url}]: {e}")
        
        return results

    def _parse_html(self, html: str, base_url: str) -> List[Dict[str, Any]]:
        """解析 FLK HTML 页面"""
        results = []
        
        # 提取法规列表项
        # FLK 可能的列表结构
        patterns = [
            # <a href="/detail/xxx">标题</a> ... 日期
            r'<a[^>]+href="(/detail/[^"]+)"[^>]*>([^<]+)</a>',
            # 列表项
            r'<li[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>.*?(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
        ]
        
        seen_titles = set()
        
        for pattern in patterns:
            matches = re.finditer(pattern, html, re.DOTALL)
            for m in matches:
                url = m.group(1)
                title = m.group(2).strip()
                
                if not title or title in seen_titles:
                    continue
                if not self._filter_by_keywords(title, []):
                    continue
                
                date = m.group(3) if len(m.groups()) >= 3 else None
                
                if date and not self._is_recent(date):
                    continue
                
                full_url = f"{self.base_url.rstrip('/')}{url}" if url.startswith('/') else url
                
                seen_titles.add(title)
                results.append({
                    'title': title,
                    'url': full_url,
                    'date': date or '',
                    'author': '全国人民代表大会',
                    'doc_number': self._extract_doc_number(title),
                    'summary': '',
                    'download_url': '',
                    'status': '现行有效',
                })
        
        return results

    def get_law_detail(self, law_id: str) -> Optional[Dict[str, Any]]:
        """
        获取法规详细信息
        
        Args:
            law_id: 法规 ID 或完整 URL
        """
        if not law_id.startswith('http'):
            law_id = f"{self.base_url}detail/{law_id}"
        
        content = self._make_request(law_id)
        if not content:
            return None
        
        # 解析详情页
        detail = {
            'url': law_id,
            'title': '',
            'author': '',
            'doc_number': '',
            'publish_date': '',
            'effective_date': '',
            'status': '现行有效',
            'download_url': '',
        }
        
        # 提取标题
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if title_m:
            detail['title'] = title_m.group(1).strip()
        
        # 提取文号
        doc_m = re.search(r'文号[：:]\s*([^\s<]+)', content)
        if doc_m:
            detail['doc_number'] = doc_m.group(1).strip()
        
        # 提取发布日期
        date_m = re.search(r'发布日期[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', content)
        if date_m:
            detail['publish_date'] = date_m.group(1)
        
        # 提取生效日期
        eff_m = re.search(r'生效日期[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', content)
        if eff_m:
            detail['effective_date'] = eff_m.group(1)
        
        # 提取 PDF 下载链接
        pdf_m = re.search(r'href="([^"]+\.pdf[^"]*)"', content)
        if pdf_m:
            detail['download_url'] = pdf_m.group(1)
        
        return detail
