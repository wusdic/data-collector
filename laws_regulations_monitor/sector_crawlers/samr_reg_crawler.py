"""
市监总局法规爬虫
来源: L5-行业标准 (市监总局数据安全相关规章)
状态: SAMR /zwgk/zcwjb/ 返回404，改用主站
"""

import logging
import re
import time
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class SamrRegCrawler(BaseCrawler):
    """国家市场监督管理总局法规爬虫"""

    NAME = "samr_reg"

    def __init__(self, config: dict, **kwargs):
        super().__init__(config, **kwargs)
        self.base_url = config.get('base_url', 'https://www.samr.gov.cn')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://www.samr.gov.cn',
        })

    def crawl(self, config: dict, **kwargs) -> list:
        """主爬取入口"""
        results = []
        keywords = kwargs.get('keywords', self.keywords) or ['数据安全', '网络市场监督管理', '电子商务', '网络安全']

        # 1. 爬主站首页
        try:
            items = self._crawl_homepage()
            results.extend(items)
            logger.info(f"  SAMR_REG 首页: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  SAMR_REG 首页失败: {e}")

        self._rate_limit()

        # 2. 爬最新通知公告
        try:
            items = self._crawl_notice_section()
            results.extend(items)
            logger.info(f"  SAMR_REG 通知公告: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  SAMR_REG 通知公告失败: {e}")

        self._rate_limit()

        return self.deduplicate(results)

    def _crawl_homepage(self) -> list:
        """爬取市监总局首页"""
        results = []
        url = 'https://www.samr.gov.cn/'
        html = self._fetch(url)
        if not html:
            return results

        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            if self.keywords and not self.matches_keywords(title):
                continue
            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.samr.gov.cn' + href

            date_m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', str(a))
            date = f"{date_m.group(1)}-{date_m.group(2):0>2}-{date_m.group(3):0>2}" if date_m else ''

            results.append({
                'title': title,
                'url': href,
                'date': date,
                'level': 'L5',
                'type': '部门规章',
                'author': '国家市场监督管理总局',
                'source_id': 'samr_reg',
                'status': self.infer_status(title),
                'doc_number': self.extract_doc_number(title),
            })
        return results

    def _crawl_notice_section(self) -> list:
        """爬取通知公告栏目"""
        results = []
        # 尝试通知公告栏目
        urls = [
            'https://www.samr.gov.cn/xw/zjfl/',
            'https://www.samr.gov.cn/xw/tzgg/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=True):
                title = a.get_text(strip=True)
                if len(title) < 5:
                    continue
                if self.keywords and not self.matches_keywords(title):
                    continue
                href = a.get('href', '')
                if href.startswith('/'):
                    href = 'https://www.samr.gov.cn' + href

                parent = a.find_parent(['li', 'tr', 'div'])
                date_str = ''
                if parent:
                    date_m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', str(parent))
                    if date_m:
                        date_str = f"{date_m.group(1)}-{date_m.group(2):0>2}-{date_m.group(3):0>2}"

                results.append({
                    'title': title,
                    'url': href,
                    'date': date_str,
                    'level': 'L5',
                    'type': '部门规章',
                    'author': '国家市场监督管理总局',
                    'source_id': 'samr_reg',
                    'status': self.infer_status(title),
                    'doc_number': self.extract_doc_number(title),
                })
        return results

    def _fetch(self, url: str) -> str:
        """HTTP GET"""
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.warning(f"  SAMR_REG fetch [{url[:60]}]: {e}")
            return ''


if __name__ == '__main__':
    import yaml
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    config = yaml.safe_load(open('/home/gem/workspace/agent/workspace/data-collector/laws_regulations_monitor/config/levels/l5_industry_standards.yaml'))
    source = config['sources'][0]
    crawler = SamrRegCrawler(source)
    results = crawler.crawl(source)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  {r.get('date','??')} | {r.get('title','??')[:60]}")