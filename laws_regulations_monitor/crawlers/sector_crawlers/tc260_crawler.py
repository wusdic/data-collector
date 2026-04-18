"""
TC260 信息安全标准化技术委员会爬虫
来源：全国信息安全标准化技术委员会官网
标准查询：https://www.tc260.org.cn/portal/project/standard
"""

import logging, re, requests
from bs4 import BeautifulSoup
from engine.base_crawler import BaseCrawler

logger = logging.getLogger('crawlers.tc260')


class TC260Crawler(BaseCrawler):
    """TC260 信息安全标准爬虫"""

    NAME = "tc260"

    def __init__(self, config: dict = None, **kwargs):
        if config is None:
            config = {}
        config.setdefault('name', '全国信息安全标准化技术委员会')
        config.setdefault('base_url', 'https://www.tc260.org.cn')
        super().__init__(config, **kwargs)

    def crawl(self, config: dict, **kwargs) -> list:
        results = []

        # 1. 从标准查询页获取
        search_url = "https://www.tc260.org.cn/portal/project/standard"
        try:
            items = self._crawl_search_page(search_url)
            results.extend(items)
            self._rate_limit()
        except Exception as e:
            logger.warning(f"TC260标准查询页失败: {e}")

        # 2. 从征求意见页获取
        suggest_url = "https://www.tc260.org.cn/portal/suggestion"
        try:
            items = self._crawl_suggestion_page(suggest_url)
            results.extend(items)
            self._rate_limit()
        except Exception as e:
            logger.warning(f"TC260征求意见页失败: {e}")

        # 3. 从首页新闻获取
        home_url = "https://www.tc260.org.cn/"
        try:
            items = self._crawl_homepage(home_url)
            results.extend(items)
        except Exception as e:
            logger.warning(f"TC260首页失败: {e}")

        logger.info(f"TC260: 获取 {len(results)} 条")
        return self.deduplicate(results)

    def _crawl_search_page(self, url: str) -> list:
        """爬取标准查询页（表单POST或直接HTML）"""
        resp = self._http_get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp, 'html.parser')
        items = []

        # 找标准列表
        selectors = [
            '.standard-list a', '.project-list a', '.result-list a',
            '.list-item a', '.article-list a', 'table a', '.data-list a',
        ]
        for selector in selectors:
            links = soup.select(selector)
            for a in links:
                title = a.get_text(strip=True)
                href = a.get('href', '')
                if not title or len(title) < 5:
                    continue
                # 标准化URL
                href = self._make_url(href, 'https://www.tc260.org.cn')
                if not href:
                    continue
                date = self._extract_date_from_text(a.get_text())
                items.append({
                    'title': title,
                    'url': href,
                    'date': date,
                    'author': '全国信息安全标准化技术委员会',
                    'level': 'L4',
                    'type': '国家标准',
                    'source': 'tc260',
                })
            if items:
                break

        # 如果没找到列表，尝试从表单结果中提取
        if not items:
            # 尝试POST搜索
            items.extend(self._try_post_search(url))

        return items

    def _try_post_search(self, url: str) -> list:
        """尝试表单搜索"""
        try:
            resp = requests.post(
                url,
                data={'keyword': '数据安全', 'pageSize': '20', 'page': '1'},
                headers={**self.headers, 'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = []
            for a in soup.find_all('a', href=True):
                title = a.get_text(strip=True)
                if title and len(title) > 5:
                    href = self._make_url(a.get('href', ''), 'https://www.tc260.org.cn')
                    if href:
                        items.append({
                            'title': title,
                            'url': href,
                            'date': '',
                            'author': '全国信息安全标准化技术委员会',
                            'level': 'L4',
                            'type': '国家标准',
                            'source': 'tc260',
                        })
            return items
        except Exception as e:
            logger.warning(f"TC260 POST搜索失败: {e}")
            return []

    def _crawl_suggestion_page(self, url: str) -> list:
        """爬取征求意见页面"""
        resp = self._http_get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp, 'html.parser')
        items = []

        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            # 判断是否征求意见稿
            is_draft = any(k in title for k in ['征求意见', '草案', 'draft'])
            href = self._make_url(a.get('href', ''), 'https://www.tc260.org.cn')
            if not href:
                continue
            date = self._extract_date_from_text(a.get_text())
            items.append({
                'title': title,
                'url': href,
                'date': date,
                'author': '全国信息安全标准化技术委员会',
                'level': 'L4',
                'type': '国家标准',
                'status': '征求意见稿' if is_draft else '现行有效',
                'source': 'tc260',
            })
        return items

    def _crawl_homepage(self, url: str) -> list:
        """从首页提取标准相关内容"""
        resp = self._http_get(url)
        if not resp:
            return []

        soup = BeautifulSoup(resp, 'html.parser')
        items = []

        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            # 筛选与标准相关的链接
            if not any(k in title for k in ['标准', '规范', '办法', '指南', '要求', '网络安全', '信息安全', '数据安全']):
                continue
            if not title or len(title) < 5:
                continue
            href = self._make_url(href, 'https://www.tc260.org.cn')
            if not href:
                continue
            date = self._extract_date_from_text(a.get_text())
            items.append({
                'title': title,
                'url': href,
                'date': date,
                'author': '全国信息安全标准化技术委员会',
                'level': 'L4',
                'type': '国家标准',
                'source': 'tc260',
            })
        return items

    def _extract_date_from_text(self, text: str) -> str:
        m = re.search(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})', text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        return ''

    def _http_get(self, url: str) -> str:
        try:
            r = requests.get(url, headers=self.headers, timeout=12)
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
    config = {'name': 'TC260', 'base_url': 'https://www.tc260.org.cn'}
    crawler = TC260Crawler(config)
    results = crawler.crawl(config)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('date','??')}] {r.get('title','')[:50]}")
