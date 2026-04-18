"""
卫健委爬虫
来源：国家卫生健康委员会政策法规
"""

import logging, re, requests
from bs4 import BeautifulSoup
from engine.base_crawler import BaseCrawler

logger = logging.getLogger('crawlers.nhc')

HEALTH_KEYWORDS = [
    "健康医疗", "医疗数据", "患者信息", "电子病历",
    "处方数据", "公共卫生", "数据安全", "个人信息",
]


class NHCCrawler(BaseCrawler):
    """卫健委法规爬虫"""

    NAME = "nhc"

    def __init__(self, config: dict = None, **kwargs):
        if config is None:
            config = {}
        config.setdefault('name', '国家卫生健康委员会')
        config.setdefault('base_url', 'https://www.nhc.gov.cn')
        super().__init__(config, **kwargs)

    def crawl(self, config: dict, **kwargs) -> list:
        results = []

        urls = [
            ("https://www.nhc.gov.cn/", "首页"),
            ("https://www.nhc.gov.cn/fks/fbhk/fbhkwbc/FYDBZCFGFBHDT/index.html", "法规标准"),
            ("https://www.nhc.gov.cn/fks/fbhk/fbhkwbc/index.html", "法规数据库"),
        ]

        for url, name in urls:
            try:
                items = self._crawl_page(url)
                if items:
                    results.extend(items)
                    self._rate_limit()
            except Exception as e:
                logger.warning(f"卫健委 [{name}] 爬取失败: {e}")

        logger.info(f"卫健委: 获取 {len(results)} 条")
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
            href = self._make_url(href, 'https://www.nhc.gov.cn')
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
                'author': '国家卫生健康委员会',
                'level': 'L3',
                'type': '部门规章',
                'status': '征求意见稿' if is_draft else '现行有效',
                'source': 'nhc',
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
    config = {'name': '卫健委', 'base_url': 'https://www.nhc.gov.cn'}
    crawler = NHCCrawler(config)
    results = crawler.crawl(config, keywords=HEALTH_KEYWORDS)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('date','??')}] {r.get('title','')[:50]}")
