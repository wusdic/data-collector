"""
市监总局法规爬虫
来源：国家市场监督管理总局
"""

import logging, re, requests
from bs4 import BeautifulSoup
from engine.base_crawler import BaseCrawler

logger = logging.getLogger('crawlers.samr_reg')

SAMR_KEYWORDS = [
    "数据安全", "网络交易", "电子商务", "个人信息",
    "市场数据", "质量监管", "标准物质",
]


class SAMRRegCrawler(BaseCrawler):
    """市监总局法规爬虫"""

    NAME = "samr_reg"

    def __init__(self, config: dict = None, **kwargs):
        if config is None:
            config = {}
        config.setdefault('name', '国家市场监督管理总局')
        config.setdefault('base_url', 'https://www.samr.gov.cn')
        super().__init__(config, **kwargs)

    def crawl(self, config: dict, **kwargs) -> list:
        results = []

        urls = [
            ("https://www.samr.gov.cn/", "首页"),
            ("https://www.samr.gov.cn/zwgk/zcwjb/", "政策法规"),
        ]

        for url, name in urls:
            try:
                items = self._crawl_page(url)
                if items:
                    results.extend(items)
                    self._rate_limit()
            except Exception as e:
                logger.warning(f"SAMR [{name}] 爬取失败: {e}")

        logger.info(f"市监总局: 获取 {len(results)} 条")
        return self.deduplicate(results)

    def _crawl_page(self, url: str) -> list:
        resp = self._http_get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp, 'html.parser')
        items = []

        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if not title or len(title) < 5:
                continue
            if self.keywords:
                if not any(k in title for k in self.keywords):
                    continue
            href = self._make_url(href, 'https://www.samr.gov.cn')
            if not href:
                continue
            date = self._extract_date_from_text(a.get_text())
            if not date:
                date = self._extract_date_from_detail(href)
            is_draft = any(k in title for k in ['征求意见', '草案'])
            items.append({
                'title': title,
                'url': href,
                'date': date,
                'author': '国家市场监督管理总局',
                'level': 'L3',
                'type': '部门规章',
                'status': '征求意见稿' if is_draft else '现行有效',
                'source': 'samr_reg',
            })
        return items

    def _extract_date_from_text(self, text: str) -> str:
        m = re.search(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        return ''

    def _extract_date_from_detail(self, url: str) -> str:
        try:
            resp = self._http_get(url)
            m = re.search(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', resp[:3000])
            if m:
                return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        except:
            pass
        return ''

    def _http_get(self, url: str) -> str:
        try:
            r = requests.get(url, headers=self.headers, timeout=12)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text
        except Exception as e:
            logger.warning(f"HTTP失败 [{url[:50]}]: {e}")
            return ''

    def _make_url(self, href: str, base: str) -> str:
        if not href or href.startswith('javascript') or href.startswith('#'):
            return ''
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            return base + href
        return base + '/' + href


if __name__ == '__main__':
    config = {'name': '市监总局', 'base_url': 'https://www.samr.gov.cn'}
    crawler = SAMRRegCrawler(config)
    results = crawler.crawl(config, keywords=SAMR_KEYWORDS)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('date','??')}] {r.get('title','')[:50]}")
