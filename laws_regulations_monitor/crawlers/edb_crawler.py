"""
执法案例库爬虫
来源: EDB-执法案例库
从CAC、市监总局等渠道采集行政处罚案例
"""

import logging
import re
import time
import requests
from typing import List, Dict, Any
from bs4 import BeautifulSoup

from engine.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class EdbCrawler(BaseCrawler):
    """执法案例库爬虫 - 采集各部委行政处罚决定书"""

    NAME = "edb"

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
        keywords = kwargs.get('keywords', self.keywords) or ['数据安全', '个人信息', 'App违法违规', '网络安全', '行政处罚', '执法案例']

        # 1. CAC 网信办处罚案例
        try:
            items = self._crawl_cac()
            results.extend(items)
            logger.info(f"  EDB CAC处罚: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB CAC失败: {e}")
        self._rate_limit()

        # 2. SAMR 市场监管总局处罚
        try:
            items = self._crawl_samr()
            results.extend(items)
            logger.info(f"  EDB SAMR处罚: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB SAMR失败: {e}")
        self._rate_limit()

        # 3. MIIT 工信部处罚
        try:
            items = self._crawl_miit()
            results.extend(items)
            logger.info(f"  EDB MIIT处罚: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB MIIT失败: {e}")
        self._rate_limit()

        # 4. MPS 公安部处罚
        try:
            items = self._crawl_mps()
            results.extend(items)
            logger.info(f"  EDB MPS处罚: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB MPS失败: {e}")
        self._rate_limit()

        # 5. SPP 最高检案例
        try:
            items = self._crawl_spp()
            results.extend(items)
            logger.info(f"  EDB SPP案例: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB SPP失败: {e}")
        self._rate_limit()

        # 6. SPC 最高法案例
        try:
            items = self._crawl_spc()
            results.extend(items)
            logger.info(f"  EDB SPC案例: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  EDB SPC失败: {e}")
        self._rate_limit()

        # 关键词过滤
        if keywords:
            filtered = []
            for r in results:
                if self.matches_keywords(r.get('title', '') + r.get('summary', '')):
                    filtered.append(r)
            results = filtered

        return self.deduplicate(results)

    # ─── CAC 网信办处罚 ───────────────────────────────────────

    def _crawl_cac(self) -> list:
        """爬取网信办行政处罚 — 优先用CAC JSON API，兜底DuckDuckGo搜索"""
        results = []
        # 方式1: 通过 CAC 规范性文件渠道 (A09370305) 找执法相关内容
        try:
            items = self._crawl_cac_by_api()
            if items:
                results.extend(items)
                logger.info(f"  CAC API: {len(items)} 条")
                return results
        except Exception as e:
            logger.warning(f"  CAC API失败: {e}")

        # 方式2: DuckDuckGo搜索处罚案例
        try:
            items = self._search_edb_via_duckduckgo()
            if items:
                results.extend(items)
                logger.info(f"  DuckDuckGo EDB搜索: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  DuckDuckGo EDB搜索失败: {e}")
        return results

    def _crawl_cac_by_api(self) -> list:
        """通过CAC JSON API获取处罚相关信息"""
        results = []
        params = {
            'channelCode': 'A09370305',  # 规范性文件
            'perPage': '20',
            'pageno': '1',
            'condition': '0',
            'fuhao': '=',
            'value': '',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Referer': 'https://www.cac.gov.cn/',
            'X-Requested-With': 'XMLHttpRequest',
        }
        try:
            r = requests.get('https://www.cac.gov.cn/cms/JsonList', params=params, headers=headers, timeout=10)
            data = r.json()
            for item in data.get('list', []):
                title = item.get('topic', '').strip()
                if not any(k in title for k in ['处罚', '行政处罚', '执法', '违法', '通报', '曝光', '决定']):
                    continue
                infourl = item.get('infourl', '')
                if infourl.startswith('//'):
                    url = f'https:{infourl}'
                elif infourl.startswith('/'):
                    url = f'https://www.cac.gov.cn{infourl}'
                else:
                    url = infourl
                pubtime = item.get('pubtime', '')
                date = pubtime.split(' ')[0] if pubtime else ''
                results.append({
                    'title': title,
                    'url': url,
                    'date': date,
                    'level': 'EDB',
                    'case_type': '行政处罚决定书',
                    'authority': '国家互联网信息办公室',
                    'source_id': 'cac_enforcement',
                    'status': '现行有效',
                })
        except Exception as e:
            logger.warning(f"CAC API调用失败: {e}")
        return results

    def _search_edb_via_duckduckgo(self) -> list:
        """通过DuckDuckGo搜索执法案例（兜底方案）"""
        results = []
        keywords = ['数据安全 行政处罚 案例', 'App违法违规 处罚决定书', '个人信息 违规 处罚 2024 2025']
        for kw in keywords[:2]:
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
                    results.append({
                        'title': title,
                        'url': url,
                        'date': date,
                        'level': 'EDB',
                        'case_type': '行政处罚决定书',
                        'authority': '各部委',
                        'summary': snippet[:200],
                        'source_id': 'duckduckgo_edb',
                        'status': '现行有效',
                    })
                self._rate_limit()
            except Exception as e:
                logger.warning(f"DuckDuckGo搜索失败 [{kw[:20]}]: {e}")
        return results

    def _parse_cac_list(self, html: str, authority: str) -> list:
        """解析CAC列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/ch/|/a20|/punish|xxgk|zwgk')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            # 过滤关键词
            if not any(kw in title for kw in ['处罚', '行政处罚', '决定书', '执法', '曝光', '案例', '违法', '违规']):
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
                'level': 'EDB',
                'case_type': '行政处罚决定书',
                'authority': authority,
                'violator': self._extract_violator(title),
                'penalty_number': self.extract_doc_number(title),
                'penalty_type': self._extract_penalty_type(title),
                'penalty_amount': self._extract_amount(title),
                'source_id': 'cac_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── SAMR 市场监管总局处罚 ─────────────────────────────────

    def _crawl_samr(self) -> list:
        """爬取市场监管总局行政处罚"""
        results = []
        urls = [
            'https://www.samr.gov.cn/zwgk/zxwj/',
            'https://www.samr.gov.cn/zwgk/zwxx/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_samr_list(html))
        return results

    def _parse_samr_list(self, html: str) -> list:
        """解析SAMR列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/zwgk/|/zwfl/')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['处罚', '行政处罚', '决定书', '执法', '曝光', '违法', '违规', '通告']):
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
                'level': 'EDB',
                'case_type': '行政处罚决定书',
                'authority': '国家市场监督管理总局',
                'violator': self._extract_violator(title),
                'penalty_number': self.extract_doc_number(title),
                'penalty_type': self._extract_penalty_type(title),
                'penalty_amount': self._extract_amount(title),
                'source_id': 'samr_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── MIIT 工信部处罚 ──────────────────────────────────────

    def _crawl_miit(self) -> list:
        """爬取工信部行政处罚"""
        results = []
        urls = [
            'https://www.miit.gov.cn/column/4634/',
            'https://www.miit.gov.cn/zwgk/zwfl/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_miit_list(html))
        return results

    def _parse_miit_list(self, html: str) -> list:
        """解析MIIT列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/zwgk/|/zwfl/')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['处罚', '行政处罚', '执法', '违法', '违规', '通告']):
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
                'level': 'EDB',
                'case_type': '行政处罚决定书',
                'authority': '工业和信息化部',
                'violator': self._extract_violator(title),
                'penalty_number': self.extract_doc_number(title),
                'penalty_type': self._extract_penalty_type(title),
                'penalty_amount': self._extract_amount(title),
                'source_id': 'miit_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── MPS 公安部处罚 ──────────────────────────────────────

    def _crawl_mps(self) -> list:
        """爬取公安部网络安全执法"""
        results = []
        urls = [
            'https://www.mps.gov.cn/zwgk/zwxx/',
            'https://www.mps.gov.cn/zwgk/zfxx/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_mps_list(html))
        return results

    def _parse_mps_list(self, html: str) -> list:
        """解析MPS列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/zwgk/|/zwfl/')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['处罚', '行政处罚', '执法', '违法', '违规', '打击', '专项行动']):
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
                'level': 'EDB',
                'case_type': '行政处罚决定书',
                'authority': '公安部',
                'violator': self._extract_violator(title),
                'penalty_number': self.extract_doc_number(title),
                'penalty_type': self._extract_penalty_type(title),
                'penalty_amount': self._extract_amount(title),
                'source_id': 'mps_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── SPP 最高检案例 ──────────────────────────────────────

    def _crawl_spp(self) -> list:
        """爬取最高检典型案例"""
        results = []
        urls = [
            'http://www.spp.gov.cn/jcxy/',
            'http://www.spp.gov.cn/fzjz/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_spp_list(html))
        return results

    def _parse_spp_list(self, html: str) -> list:
        """解析SPP列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/jcxy/|/fzjz/|/art20|/art')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['数据', '信息', '个人', '网络', '案例', '典型', '安全', '违法', '犯罪']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'http://www.spp.gov.cn' + href

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
                'level': 'EDB',
                'case_type': '典型案例',
                'authority': '最高人民检察院',
                'violator': '',
                'penalty_number': '',
                'penalty_type': [],
                'penalty_amount': '',
                'source_id': 'spp_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── SPC 最高法案例 ──────────────────────────────────────

    def _crawl_spc(self) -> list:
        """爬取最高法典型案例"""
        results = []
        urls = [
            'https://www.court.gov.cn/fabu/jiedu/',
            'https://www.court.gov.cn/fabu/xinwen/',
        ]
        for url in urls:
            html = self._fetch(url)
            if not html:
                continue
            results.extend(self._parse_spc_list(html))
        return results

    def _parse_spc_list(self, html: str) -> list:
        """解析SPC列表"""
        results = []
        soup = BeautifulSoup(html, 'html.parser')

        for a in soup.find_all('a', href=re.compile(r'/fabu/|/jcdu/')):
            title = a.get_text(strip=True)
            if len(title) < 6:
                continue
            if not any(kw in title for kw in ['数据', '信息', '个人', '网络', '案例', '典型', '安全', '违法']):
                continue

            href = a.get('href', '')
            if href.startswith('/'):
                href = 'https://www.court.gov.cn' + href

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
                'level': 'EDB',
                'case_type': '典型案例',
                'authority': '最高人民法院',
                'violator': '',
                'penalty_number': '',
                'penalty_type': [],
                'penalty_amount': '',
                'source_id': 'spc_enforcement',
                'status': '现行有效',
            })
        return results

    # ─── 辅助方法 ────────────────────────────────────────────

    def _extract_violator(self, title: str) -> str:
        """从标题提取被处罚主体"""
        # 常见模式: "XXX公司 处罚" / "对XXX的处罚"
        m = re.search(r'([\u4e00-\u9fa5]{2,20}(公司|企业|集团|单位|个人))', title)
        if m:
            return m.group(1)
        m = re.search(r'对(.+?)的处罚', title)
        if m:
            return m.group(1)
        return ''

    def _extract_penalty_type(self, title: str) -> list:
        """从标题提取处罚类型"""
        types = []
        if '罚款' in title:
            types.append('罚款')
        if '警告' in title:
            types.append('警告')
        if '责令' in title or '整改' in title:
            types.append('责令改正')
        if '下架' in title:
            types.append('下架')
        if '吊销' in title:
            types.append('吊销许可证')
        if '行政拘留' in title:
            types.append('行政拘留')
        return types

    def _extract_amount(self, title: str) -> str:
        """从标题提取罚款金额"""
        m = re.search(r'(\d+(?:\.\d+)?)\s*万元', title)
        if m:
            return m.group(1)
        m = re.search(r'罚款\s*(\d+(?:\.\d+)?)', title)
        if m:
            return m.group(1)
        return ''

    def _fetch(self, url: str) -> str:
        """HTTP GET"""
        try:
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logger.warning(f"  EDB fetch [{url[:60]}]: {e}")
            return ''


if __name__ == '__main__':
    import yaml
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    config = yaml.safe_load(open('/home/gem/workspace/agent/workspace/data-collector/laws_regulations_monitor/config/levels/edb_enforcement_cases.yaml'))
    source = config['sources'][0]
    crawler = EdbCrawler(source)
    results = crawler.crawl(source)
    print(f"获取 {len(results)} 条")
    for r in results[:5]:
        print(f"  [{r.get('authority','??')}] {r.get('date','??')} | {r.get('title','??')[:60]}")
