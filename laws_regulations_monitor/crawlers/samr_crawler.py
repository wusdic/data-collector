"""
国家标准全文公开系统爬虫
http://openstd.samr.gov.cn/bzgk/std/
来源: L4-国家标准
"""

import re
import logging
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class SAMRCrawler(BaseCrawler):
    """国家标准全文公开系统爬虫"""

    def __init__(self, config: Dict[str, Any], lookback_days: int = 730):
        super().__init__(config, lookback_days)
        self.base_url = config.get('base_url', 'http://openstd.samr.gov.cn/bzgk/std/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/1.0)',
            'Accept': 'text/html,application/xhtml+xml',
        })

    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """爬取国家标准"""
        results = []
        keywords = ['数据安全', '网络安全', '个人信息', '信息安全', '人工智能']

        for kw in keywords:
            try:
                items = self._search_by_keyword(kw, max_pages=2)
                for item in items:
                    item['level'] = 'L4'
                    item['type'] = '国家标准'
                    item['author'] = '国家市场监督管理总局'
                results.extend(items)
                logger.info(f"  SAMR [{kw}]: {len(items)} 条")
            except Exception as e:
                logger.warning(f"  SAMR [{kw}] 失败: {e}")
            self._rate_limit()

        return self._deduplicate(results)

    def _search_by_keyword(self, keyword: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        # 优先走 API，失败自动 fallback
        return self._search_api(keyword, max_pages)

    def _fetch_page(self, keyword: str, page_num: int) -> List[Dict[str, Any]]:
        params = {
            'p.p1': '0',
            'p.p90': 'circulation_date',
            'p.p91': 'desc',
            'p.p2': keyword,
            'page': str(page_num),
            'pageSize': '20',
        }
        r = self.session.get(f'{self.base_url}std_list', params=params, timeout=10)
        r.raise_for_status()
        return self._parse_list_page(r.text)

    def _parse_list_page(self, html: str) -> List[Dict[str, Any]]:
        """
        解析标准列表页
        每行标准有3个showInfo，第2个包含标题+状态+日期信息：
        showInfo(hcno);">标题</a> 推标/强标 即将实施 发布日期 实施日期
        """
        results = []
        all_positions = [(m.start(), m.group(1)) for m in re.finditer(r"showInfo\('([A-F0-9]+)'\)", html)]

        for i in range(0, len(all_positions) - 2, 3):
            if i + 2 >= len(all_positions):
                break

            p_std, hcno_std = all_positions[i]
            p_title, hcno_title = all_positions[i + 1]
            p_status, hcno_status = all_positions[i + 2]

            # 标准号：从标准号列的上下文
            std_snippet = html[max(0, p_std - 200):p_std + 200]
            gb_m = re.search(r'(GB\s*4\d+[\d\-]+)', std_snippet)
            if not gb_m:
                gb_m = re.search(r'(GB/T?\s*[\d\.\-]+)', std_snippet)
            std_num = gb_m.group(1) if gb_m else ''

            # 标题+日期：第2个showInfo后包含完整信息（扩展到1000字符以包含日期）
            title_snippet = html[p_title:p_title + 1000]
            # 标题
            title_m = re.search(r'showInfo\([\"\'].+?[\"\']\);">([^<\r\n]+)', title_snippet)
            title = title_m.group(1).strip() if title_m else ''
            if not title:
                continue

            # 发布日期在标题之后的文本中
            date_m = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\.\d', title_snippet)
            date = date_m.group(1) if date_m else ''

            results.append({
                'title': re.sub(r'\s+', ' ', title),
                'url': f'{self.base_url}newGbInfo?hcno={hcno_title}',
                'date': date,
                'doc_number': std_num,
                'author': '国家市场监督管理总局',
                'level': 'L4',
                'type': '国家标准',
                'status': '现行有效',
                'summary': '',
                'download_url': '',
            })

        return results

    def _search_api(self, keyword: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        """
        优先通过 open.samr.gov.cn API 搜索，失败则 fallback 到 HTML 爬取。
        """
        try:
            results = self._search_open_api(keyword, max_pages)
            if results:
                return results
        except Exception as e:
            logger.warning(f"  open.samr.gov.cn API 失败 [{keyword}], 切换 fallback: {e}")

        # Fallback: 从 www.samr.gov.cn 搜索页 HTML 提取
        return self._fallback_html_search(keyword, max_pages)

    def _search_open_api(self, keyword: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        """open.samr.gov.cn 正式 API"""
        results = []
        for page in range(1, max_pages + 1):
            items = self._fetch_page(keyword, page)
            if not items:
                break
            results.extend(items)
        return results

    def _fallback_html_search(self, keyword: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        """
        Fallback: 从 www.samr.gov.cn 搜索页 HTML 提取。
        当 open.samr.gov.cn DNS 不通时使用。
        """
        search_url = f"https://www.samr.gov.cn/search/"
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LawMonitor/1.0)",
            "Accept": "text/html",
        }

        for page in range(1, max_pages + 1):
            try:
                params = {"q": keyword, "page": str(page)}
                resp = requests.get(search_url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"  www.samr.gov.cn 请求失败 [{keyword} page={page}]: {e}")
                break

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 尝试多种选择器（SAMR 搜索页结构可能有变化）
            items = (
                soup.select('.search-result .item') or
                soup.select('.result-item') or
                soup.select('article') or
                soup.select('.list-item')
            )

            if not items:
                # 通用：找所有含链接的条目
                items = soup.select('a[href*="/std/"]')

            for item in items[:20]:
                title_el = item.select_one('h3, .title, .t, [class*="title"]') or item
                title = title_el.get_text(strip=True) if title_el else item.get_text(strip=True)
                if not title:
                    continue

                # 提取链接
                link_el = item.select_one('a[href]') if title_el != item else item
                href = link_el.get('href', '') if link_el else ''
                if href and not href.startswith('http'):
                    href = 'https://www.samr.gov.cn' + href

                # 摘要
                snippet_el = item.select_one('.snippet, .desc, .summary, [class*="desc"]')
                snippet = snippet_el.get_text(strip=True) if snippet_el else ''

                # 日期（尝试从文本中提取）
                import re
                date_m = re.search(r'(\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日)', item.get_text())
                date = date_m.group(1) if date_m else ''

                results.append({
                    'title': re.sub(r'\s+', ' ', title),
                    'url': href,
                    'date': date,
                    'doc_number': '',
                    'author': '国家市场监督管理总局',
                    'level': 'L4',
                    'type': '国家标准',
                    'status': '现行有效',
                    'summary': snippet,
                    'download_url': '',
                })

        logger.info(f"  SAMR fallback [{keyword}]: {len(results)} 条")
        return results

    def _deduplicate(self, results: List[Dict]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []
        for r in results:
            key = r['title']
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique
