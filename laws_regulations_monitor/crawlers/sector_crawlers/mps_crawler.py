"""
公安部行业标准爬虫
来源: L5-行业标准 (公安部GA/T标准)
状态: MPS (mps.gov.cn) 目前返回521错误，暂标记为不可用
"""

import logging
import re
import time
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class MpsCrawler(BaseCrawler):
    """公安部网络安全/公安行业标准爬虫"""

    NAME = "mps"

    def __init__(self, config: dict, **kwargs):
        super().__init__(config, **kwargs)
        self.base_url = config.get('base_url', 'https://www.mps.gov.cn')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://www.mps.gov.cn',
        })

    def crawl(self, config: dict, **kwargs) -> list:
        """主爬取入口"""
        results = []
        keywords = kwargs.get('keywords', self.keywords) or ['网络安全', '数据安全管理', '等级保护', 'GA/T']

        # MPS is currently returning 521 (origin unreachable) - log and return empty
        try:
            r = self.session.get('https://www.mps.gov.cn/', timeout=8)
            if r.status_code == 521:
                logger.warning("  MPS: 服务器返回521错误，站点暂时不可访问")
                return results
        except Exception as e:
            logger.warning(f"  MPS 无法连接: {e}")
            return results

        # 如果可访问，则正常爬取
        try:
            items = self._crawl_homepage()
            results.extend(items)
            logger.info(f"  MPS 首页: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  MPS 首页失败: {e}")

        self._rate_limit()

        try:
            items = self._crawl_security_section()
            results.extend(items)
            logger.info(f"  MPS 安全专栏: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  MPS 安全专栏失败: {e}")

        return self.deduplicate(results)

    def _crawl_homepage(self) -> list:
        """爬取公安部首页通知公告"""
        results = []
        url = 'https://www.mps.gov.cn/'
        html = self._fetch(url)
        if not html:
            return results

        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=re.compile(r'/n\d+/|zwgk|fl')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if self.keywords and not self.matches_keywords(title):
                continue
            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.mps.gov.cn' + href

            date_m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', str(a))
            date = f"{date_m.group(1)}-{date_m.group(2):0>2}-{date_m.group(3):0>2}" if date_m else ''

            results.append({
                'title': title,
                'url': href,
                'date': date,
                'level': 'L5',
                'type': '公安行业标准',
                'author': '公安部',
                'source_id': 'mps_security_std',
                'status': self.infer_status(title),
                'doc_number': self.extract_doc_number(title),
            })
        return results

    def _crawl_security_section(self) -> list:
        """爬网络安全/等级保护专栏"""
        results = []
        section_urls = [
            'https://www.mps.gov.cn/n6557558/',
            'https://www.mps.gov.cn/zwgk/zwxx/',
            'https://www.mps.gov.cn/zwgk/zfxx/',
        ]
        for url in section_urls:
            html = self._fetch(url)
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=re.compile(r'zwgk|n\d+')):
                title = a.get_text(strip=True)
                if len(title) < 6:
                    continue
                if self.keywords and not self.matches_keywords(title):
                    continue
                href = a.get('href', '')
                if href.startswith('/'):
                    href = 'https://www.mps.gov.cn' + href

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
                    'type': '公安行业标准',
                    'author': '公安部',
                    'source_id': 'mps_security_std',
                    'status': self.infer_status(title),
                    'doc_number': self.extract_doc_number(title),
                })
        return results

    def _fetch(self, url: str) -> str:
        """HTTP GET"""
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            if r.encoding in (None, 'ISO-8859-1', 'latin1'):
                r.encoding = 'utf-8'
            return r.text
        except Exception as e:
            logger.warning(f"  MPS fetch [{url[:60]}]: {e}")
            return ''


if __name__ == '__main__':
    import yaml
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    config = yaml.safe_load(open('/home/gem/workspace/agent/workspace/data-collector/laws_regulations_monitor/config/levels/l5_industry_standards.yaml'))
    source = config['sources'][3]
    crawler = MpsCrawler(source)
    results = crawler.crawl(source)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  {r.get('date','??')} | {r.get('title','??')[:60]}")