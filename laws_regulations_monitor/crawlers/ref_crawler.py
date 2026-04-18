"""
参考资料库爬虫
来源: REF-参考资料库
从中国信通院、电子标准院、赛博研究院等采集白皮书/研究报告
"""

import logging
import re
import time
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class RefCrawler(BaseCrawler):
    """参考资料库爬虫 - 采集白皮书/研究报告/指南"""

    NAME = "ref"

    def __init__(self, config: dict, **kwargs):
        super().__init__(config, **kwargs)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

    def crawl(self, config: dict, **kwargs) -> list:
        """主爬取入口"""
        results = []
        keywords = kwargs.get('keywords', self.keywords) or [
            '数据安全', '个人信息保护', '网络安全', '白皮书', '技术报告', '研究报告',
            '合规指南', '最佳实践', '数据安全能力'
        ]

        # 1. 中国信通院 CAICT
        try:
            items = self._crawl_caict()
            results.extend(items)
            logger.info(f"  REF CAICT信通院: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF CAICT失败: {e}")
        self._rate_limit()

        # 2. 电子标准院 CESI
        try:
            items = self._crawl_cesi()
            results.extend(items)
            logger.info(f"  REF CESI电子标准院: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF CESI失败: {e}")
        self._rate_limit()

        # 3. 赛博研究院
        try:
            items = self._crawl_cyberspp()
            results.extend(items)
            logger.info(f"  REF 赛博研究院: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF 赛博研究院失败: {e}")
        self._rate_limit()

        # 4. 国家保密局 NCAC
        try:
            items = self._crawl_ncac()
            results.extend(items)
            logger.info(f"  REF NCAC保密局: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF NCAC失败: {e}")
        self._rate_limit()

        # 5. 工信部指导性文件
        try:
            items = self._crawl_miit_guide()
            results.extend(items)
            logger.info(f"  REF MIIT指导文件: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF MIIT指导文件失败: {e}")
        self._rate_limit()

        # 6. DuckDuckGo搜索参考资料（兜底）
        try:
            items = self._search_ref_via_duckduckgo()
            if items:
                results.extend(items)
                logger.info(f"  REF DuckDuckGo搜索: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF DuckDuckGo失败: {e}")

        # 7. CAC网信办政策法规库
        try:
            items = self._crawl_cac()
            results.extend(items)
            logger.info(f"  REF CAC政策法规: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  REF CAC失败: {e}")
        self._rate_limit()

        # 关键词过滤
        if keywords:
            filtered = []
            for r in results:
                if self.matches_keywords(r.get('title', '') + r.get('summary', '')):
                    filtered.append(r)
            results = filtered

        return self.deduplicate(results)

    # ─── 中国信通院 CAICT ────────────────────────────────────

    def _crawl_caict(self) -> list:
        """爬取中国信通院"""
        results = []
        urls = [
            'https://www.caict.ac.cn/',
            'https://www.caict.ac.cn/xxgk/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_caict_list(html, '中国信息通信研究院'))
            break
        return results

    def _parse_caict_list(self, html: str, author: str) -> list:
        """解析CAICT列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/a20|/xxgk/|/report|/white|/research|/news')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            # 优先数据安全/网络安全相关内容
            if not any(kw in title for kw in ['数据安全', '网络', '信息', '安全', '个人', '白皮书', '报告', '研究', '治理']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.caict.ac.cn' + href

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
                'level': 'REF',
                'doc_type': self._infer_doc_type(title),
                'author': author,
                'summary': '',
                'source_id': 'caict_docs',
                'status': '现行有效',
            })
        return results

    # ─── 电子标准院 CESI ─────────────────────────────────────

    def _crawl_cesi(self) -> list:
        """爬取电子标准院"""
        results = []
        urls = [
            'https://www.cesi.cn/',
            'https://www.cesi.cn/page/index.html',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_cesi_list(html, '中国电子技术标准化研究院'))
            break
        return results

    def _parse_cesi_list(self, html: str, author: str) -> list:
        """解析CESI列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/cesi/|/news|/report|/standard|/research')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['数据安全', '网络', '信息', '安全', '个人', '白皮书', '报告', '研究', '标准', '技术']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.cesi.cn' + href

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
                'level': 'REF',
                'doc_type': self._infer_doc_type(title),
                'author': author,
                'summary': '',
                'source_id': 'cesi_docs',
                'status': '现行有效',
            })
        return results

    # ─── 赛博研究院 ─────────────────────────────────────────

    def _crawl_cyberspp(self) -> list:
        """爬取赛博研究院"""
        results = []
        # 尝试多个可能的URL
        urls = [
            'https://www.cyberpolice.cn/',
            'https://www.cyberspp.cn/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_cyberspp_list(html, '赛博研究院'))
            if results:
                break
        return results

    def _parse_cyberspp_list(self, html: str, author: str) -> list:
        """解析赛博研究院列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/news|/report|/research|/policy|/cyber|/article')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['数据安全', '网络', '信息', '安全', '个人', '白皮书', '报告', '研究', '治理', '产业']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.cyberspp.cn' + href

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
                'level': 'REF',
                'doc_type': self._infer_doc_type(title),
                'author': author,
                'summary': '',
                'source_id': 'cyberspp_docs',
                'status': '现行有效',
            })
        return results

    # ─── 国家保密局 NCAC ────────────────────────────────────

    def _crawl_ncac(self) -> list:
        """爬取国家保密局"""
        results = []
        urls = [
            'http://www.ncac.gov.cn/',
            'http://www.ncac.gov.cn/column/21',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_ncac_list(html, '国家保密局'))
            break
        return results

    def _parse_ncac_list(self, html: str, author: str) -> list:
        """解析NCAC列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/column/|/art20|/art/|/policy')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['数据安全', '网络', '信息', '安全', '个人', '政策法规', '法规', '规章', '规定']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'http://www.ncac.gov.cn' + href

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
                'level': 'REF',
                'doc_type': '政策法规',
                'author': author,
                'summary': '',
                'source_id': 'ncac_docs',
                'status': '现行有效',
            })
        return results

    # ─── 工信部指导性文件 ────────────────────────────────────

    def _crawl_miit_guide(self) -> list:
        """爬取工信部指导性文件"""
        results = []
        urls = [
            'https://www.miit.gov.cn/zwgk/zwfl/',
            'https://www.miit.gov.cn/column/69/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_miit_guide_list(html, '工业和信息化部'))
        return results

    def _parse_miit_guide_list(self, html: str, author: str) -> list:
        """解析MIIT指导文件列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/zwgk/|/zwfl/')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['指南', '指导意见', '办法', '通知', '数据安全', '网络安全', '个人信息']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.miit.gov.cn' + href

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
                'level': 'REF',
                'doc_type': '指导性文件',
                'author': author,
                'summary': '',
                'source_id': 'miit_guide',
                'status': '现行有效',
            })
        return results

    # ─── CAC 网信办政策法规库 ────────────────────────────────

    def _crawl_cac(self) -> list:
        """爬取网信办政策法规库"""
        results = []
        urls = [
            'https://www.cac.gov.cn/',
            'https://www.cac.gov.cn/channels/channels.html',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_cac_list(html, '国家互联网信息办公室'))
            break
        return results

    def _parse_cac_list(self, html: str, author: str) -> list:
        """解析CAC列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/ch/|/a20|/policy|/guide')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['指南', '指导意见', '办法', '通知', '数据安全', '网络安全', '个人信息', '白皮书', '报告', '政策']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.cac.gov.cn' + href

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
                'level': 'REF',
                'doc_type': self._infer_doc_type(title),
                'author': author,
                'summary': '',
                'source_id': 'cac_policy_docs',
                'status': '现行有效',
            })
        return results

    def _search_ref_via_duckduckgo(self) -> list:
        """通过DuckDuckGo搜索参考资料（兜底方案）"""
        results = []
        keywords = [
            '数据安全白皮书 2024 2025 site:caict.ac.cn OR site:cesi.cn OR site:cyber',
            '个人信息保护指南 研究报告',
            '网络安全能力建设 白皮书',
            '数据安全治理 最佳实践',
        ]
        for kw in keywords[:3]:
            try:
                resp = requests.get(
                    'https://duckduckgo.com/html/',
                    params={'q': kw, 'kl': 'zh-cn'},
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=10
                )
                soup = BeautifulSoup(resp.text, 'html.parser')
                for item in soup.select('.result')[:10]:
                    title_el = item.select_one('.result__title a')
                    snippet_el = item.select_one('.result__snippet')
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    url = title_el.get('href', '')
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ''
                    date_m = re.search(r'(20\d{2}[-年]\d{1,2}[-月]\d{1,2})', snippet)
                    date = date_m.group(1).replace('年', '-').replace('月', '-') if date_m else ''
                    doc_type = self._infer_doc_type(title)
                    results.append({
                        'title': title,
                        'url': url,
                        'date': date,
                        'level': 'REF',
                        'type': doc_type,
                        'author': '网络搜索',
                        'summary': snippet[:200],
                        'source_id': 'duckduckgo_ref',
                        'status': '现行有效',
                    })
                self._rate_limit()
            except Exception as e:
                logger.warning(f"DuckDuckGo搜索失败 [{kw[:20]}]: {e}")
        return results

    # ─── 辅助方法 ────────────────────────────────────────────

    def _infer_doc_type(self, title: str) -> str:
        """从标题推断文档类型"""
        if '白皮书' in title:
            return '白皮书'
        if '蓝皮书' in title:
            return '蓝皮书'
        if '报告' in title:
            return '研究报告'
        if '指南' in title or '指引' in title:
            return '指南'
        if '最佳实践' in title:
            return '最佳实践'
        if '技术报告' in title or '研究报告' in title:
            return '技术报告'
        if '研究成果' in title:
            return '研究成果'
        if '解读' in title:
            return '解读'
        if '指导意见' in title or '意见' in title:
            return '指导性文件'
        return '研究报告'

    def _fetch(self, url: str) -> str:
        """HTTP GET"""
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            if r.encoding in (None, 'ISO-8859-1', 'latin1'):
                r.encoding = 'utf-8'
            return r.text
        except Exception as e:
            logger.warning(f"  REF fetch [{url[:60]}]: {e}")
            return ''


if __name__ == '__main__':
    import yaml
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    config = yaml.safe_load(open('/home/gem/workspace/agent/workspace/data-collector/laws_regulations_monitor/config/levels/ref_reference_materials.yaml'))
    source = config['sources'][0]
    crawler = RefCrawler(source)
    results = crawler.crawl(source)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('author','??')}] {r.get('date','??')} | {r.get('title','??')[:60]}")
