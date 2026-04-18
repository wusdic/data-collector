"""
人民银行金融行业标准爬虫
来源: L5-行业标准 (金融行业标准 JR/T)
"""

import logging
import re
import time
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class PbcCrawler(BaseCrawler):
    """中国人民银行金融行业标准爬虫"""

    NAME = "pbc"

    def __init__(self, config: dict, **kwargs):
        super().__init__(config, **kwargs)
        self.base_url = config.get('base_url', 'http://www.pbc.gov.cn')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'http://www.pbc.gov.cn',
        })

    def crawl(self, config: dict, **kwargs) -> list:
        """主爬取入口"""
        results = []

        # 1. 爬首页（主要来源）
        try:
            items = self._crawl_homepage()
            results.extend(items)
            logger.info(f"  PBC 首页: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  PBC 首页失败: {e}")

        self._rate_limit()

        # 2. 爬法律法规栏目（货币政策委员会、金融稳定等）
        try:
            items = self._crawl_policy_section()
            results.extend(items)
            logger.info(f"  PBC 法律法规: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  PBC 法律法规失败: {e}")

        self._rate_limit()

        return self.deduplicate(results)

    def _crawl_homepage(self) -> list:
        """爬取人民银行首页"""
        results = []
        url = 'http://www.pbc.gov.cn/'
        html = self._fetch(url)
        if not html:
            return results

        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            href = a.get('href', '')
            if href.startswith('/'):
                href = 'http://www.pbc.gov.cn' + href

            # 过滤数据安全/金融相关信息
            if not any(kw in title for kw in ['数据安全', '金融数据', '个人金融', '征信', '反洗钱', '网络安全', '信息安全', 'JR/T', '金融稳定', '银行监管']):
                continue

            date_m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', str(a))
            date = f"{date_m.group(1)}-{date_m.group(2):0>2}-{date_m.group(3):0>2}" if date_m else ''

            results.append({
                'title': title,
                'url': href,
                'date': date,
                'level': 'L5',
                'type': '金融行业标准',
                'author': '中国人民银行',
                'source_id': 'pbc_financial_std',
                'status': self.infer_status(title),
                'doc_number': self.extract_doc_number(title),
            })
        return results

    def _crawl_policy_section(self) -> list:
        """爬取货币政策/宏观审慎栏目"""
        results = []
        urls = [
            'http://www.pbc.gov.cn/tiaofasi/144941/index.html',   # 法律法规（货币政策）
            'http://www.pbc.gov.cn/huobizhengceersi/214481/index.html',  # 宏观审慎
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
                href = a.get('href', '')
                if href.startswith('/'):
                    href = 'http://www.pbc.gov.cn' + href

                parent = a.find_parent(['li', 'tr', 'div'])
                date_str = ''
                if parent:
                    date_m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', str(parent))
                    if date_m:
                        date_str = f"{date_m.group(1)}-{date_m.group(2):0>2}-{date_m.group(3):0>2}"

                if not any(kw in title for kw in ['数据安全', '金融数据', '征信', '反洗钱', '网络安全', 'JR/T', '金融稳定', '银行', '支付']):
                    if self.keywords and not self.matches_keywords(title):
                        continue

                results.append({
                    'title': title,
                    'url': href,
                    'date': date_str,
                    'level': 'L5',
                    'type': '金融行业标准',
                    'author': '中国人民银行',
                    'source_id': 'pbc_financial_std',
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
            logger.warning(f"  PBC fetch [{url[:60]}]: {e}")
            return ''


if __name__ == '__main__':
    import yaml
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    config = yaml.safe_load(open('/home/gem/workspace/agent/workspace/data-collector/laws_regulations_monitor/config/levels/l5_industry_standards.yaml'))
    source = config['sources'][1]
    crawler = PbcCrawler(source)
    results = crawler.crawl(source)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  {r.get('date','??')} | {r.get('title','??')[:70]}")