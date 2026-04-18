"""
工信部爬虫
来源：工业和信息化部政策文件栏目
"""

import logging, re, requests
from bs4 import BeautifulSoup
from engine.base_crawler import BaseCrawler

logger = logging.getLogger('crawlers.miit')

# 工信部已知可访问的政策文件URL
MIIT_POLICY_URLS = [
    "https://www.miit.gov.cn/zwgk/zcwj/",
    "https://www.miit.gov.cn/zwgk/zcwj/index.html",
]

# 搜索关键词（数据安全相关）
DATA_SECURITY_KEYWORDS = [
    "数据安全", "网络安全", "个人信息", "信息安全",
    "工业数据", "车联网", "智能网联汽车", "工业互联网",
]


class MIITCrawler(BaseCrawler):
    """工信部法规爬虫"""

    NAME = "miit"

    def __init__(self, config: dict = None, **kwargs):
        if config is None:
            config = {}
        config.setdefault('name', '工信部政策法规')
        config.setdefault('base_url', 'https://www.miit.gov.cn')
        super().__init__(config, **kwargs)

    def crawl(self, config: dict, **kwargs) -> list:
        results = []

        for base_url in MIIT_POLICY_URLS:
            try:
                items = self._crawl_page(base_url)
                results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"工信部爬取失败 [{base_url}]: {e}")

        # 关键词过滤
        if self.keywords:
            filtered = [r for r in results if self.matches_keywords(r.get('title', ''))]
            logger.info(f"工信部: {len(results)} 条原始 → {len(filtered)} 条关键词过滤后")
            results = filtered
        else:
            logger.info(f"工信部: 获取 {len(results)} 条")

        return self.deduplicate(results)

    def _crawl_page(self, url: str) -> list:
        """爬取单个列表页"""
        resp = self._http_get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp, 'html.parser')
        items = []

        # 工信部网站常见列表选择器
        selectors = [
            '.list-item a', '.article-list a', '.news-list a',
            '.zwgk-list a', 'ul li a', '.policy-list a',
            'table a', '.content a',
        ]

        for selector in selectors:
            links = soup.select(selector)
            if links:
                for a in links:
                    title = a.get_text(strip=True)
                    href = a.get('href', '')
                    if not title or len(title) < 5:
                        continue
                    # 标准化URL
                    href = self._make_url(href, 'https://www.miit.gov.cn')
                    if not href:
                        continue
                    # 过滤非政策文件
                    if any(k in title for k in ['通知', '公告', '公示', '征求意见']):
                        pass  # 保留
                    items.append({
                        'title': title,
                        'url': href,
                        'date': self._extract_date_from_text(a.get_text()),
                        'author': '工业和信息化部',
                        'level': 'L3',
                        'type': '部门规章',
                        'source': 'miit',
                    })
                if items:
                    break

        # 也从正文页提取日期
        for item in items:
            if not item.get('date'):
                item['date'] = self._extract_date_from_detail(item['url'])

        return items

    def _extract_date_from_text(self, text: str) -> str:
        """从文本片段中提取日期"""
        m = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        return ''

    def _extract_date_from_detail(self, url: str) -> str:
        """从详情页提取日期"""
        try:
            resp = self._http_get(url)
            if not resp:
                return ''
            m = re.search(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})', resp[:3000])
            if m:
                return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        except:
            pass
        return ''

    def _http_get(self, url: str) -> str:
        """带UA的GET"""
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            r.encoding = r.apparent_encoding or 'utf-8'
            return r.text
        except Exception as e:
            logger.warning(f"HTTP失败 [{url}]: {e}")
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
    import yaml, sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

    config = {'name': '工信部', 'base_url': 'https://www.miit.gov.cn'}
    crawler = MIITCrawler(config)
    results = crawler.crawl(config)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('date','??')}] {r.get('title','')[:50]}")
