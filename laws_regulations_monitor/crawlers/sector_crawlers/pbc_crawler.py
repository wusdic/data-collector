"""
人民银行/金融监管爬虫
来源：中国人民银行官网 + 国家金融监督管理总局
"""

import logging, re, requests
from bs4 import BeautifulSoup
from engine.base_crawler import BaseCrawler

logger = logging.getLogger('crawlers.pbc')

# 金融数据安全相关关键词
FINANCIAL_KEYWORDS = [
    "数据安全", "金融数据", "个人金融信息", "银行数据",
    "征信信息", "反洗钱", "数据治理", "网络安全",
]


class PBCCrawler(BaseCrawler):
    """人民银行金融数据标准爬虫"""

    NAME = "pbc"

    def __init__(self, config: dict = None, **kwargs):
        if config is None:
            config = {}
        config.setdefault('name', '中国人民银行')
        config.setdefault('base_url', 'https://www.pbc.gov.cn')
        super().__init__(config, **kwargs)

    def crawl(self, config: dict, **kwargs) -> list:
        results = []

        # 人民银行首页
        urls = [
            ("https://www.pbc.gov.cn/", "首页"),
            ("https://www.pbc.gov.cn/zhengwugongkai/4081330/4081338/index.html", "政务公开"),
            ("https://www.pbc.gov.cn/zhengcehuobisi/125207/3870933/3870939/index.html", "金融稳定"),
        ]

        for url, name in urls:
            try:
                items = self._crawl_page(url)
                if items:
                    results.extend(items)
                    self._rate_limit()
            except Exception as e:
                logger.warning(f"PBC [{name}] 爬取失败: {e}")

        logger.info(f"人民银行: 获取 {len(results)} 条")
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
            # 关键词过滤
            if self.keywords:
                if not any(k in title for k in self.keywords):
                    continue
            href = self._make_url(href, 'https://www.pbc.gov.cn')
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
                'author': '中国人民银行',
                'level': 'L3',
                'type': '部门规章' if not is_draft else '征求意见稿',
                'status': '征求意见稿' if is_draft else '现行有效',
                'source': 'pbc',
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
            if not resp:
                return ''
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
    config = {'name': '人民银行', 'base_url': 'https://www.pbc.gov.cn'}
    crawler = PBCCrawler(config)
    results = crawler.crawl(config, keywords=FINANCIAL_KEYWORDS)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('date','??')}] {r.get('title','')[:50]}")
