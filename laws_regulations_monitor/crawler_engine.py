"""
法规监控系统 - 并发爬虫引擎
配置驱动，支持多来源并发抓取

用法:
  python3 -m laws_regulations_monitor.crawler_engine --levels L1,L2,L3,L4
  python3 -m laws_regulations_monitor.crawler_engine --sources cac_l1,samr_standards
  python3 -m laws_regulations_monitor.crawler_engine --all
"""

import os
import re
import sys
import json
import time
import logging
import argparse
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

import requests

# Setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config_manager import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/crawler_engine.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger('crawler_engine')

# ═══════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'data_sources.yaml')
OUTPUT_DIR = os.path.join(BASE_DIR, 'data')

HEADERS_DEFAULT = {
    'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/2.0)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


# ═══════════════════════════════════════════════════════════════════
# 爬虫实现
# ═══════════════════════════════════════════════════════════════════

class BaseFetcher:
    """HTTP fetcher with encoding detection"""

    def __init__(self, config: Dict):
        self.session = requests.Session()
        self.session.headers.update(HEADERS_DEFAULT)
        if config.get('headers'):
            self.session.headers.update(config['headers'])
        self.timeout = config.get('timeout', 15)
        self.retry = config.get('retry', 3)
        self.encoding = config.get('encoding', 'auto')

    def fetch(self, url: str, encoding: str = 'auto') -> Optional[str]:
        for attempt in range(self.retry):
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                r.raise_for_status()
                if encoding == 'auto':
                    # Auto-detect encoding
                    for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                        try:
                            r.encoding = enc
                            test = r.text[:1000]
                            if '\u4e00' <= test[200] <= '\u9fff' if len(test) > 200 else True:
                                break
                        except:
                            pass
                else:
                    r.encoding = encoding
                return r.text
            except Exception as e:
                if attempt == self.retry - 1:
                    logger.warning(f"  Fetch failed: {url[:60]} - {e}")
                time.sleep(1)
        return None


class CACSrawler:
    """网信办 JSON API 爬虫 - 已知可用"""

    CHANNEL_MAP = {
        'A09370301': ('法律', 'L1', '国家法律'),
        'A09370302': ('行政法规', 'L2', '行政法规'),
        'A09370303': ('部门规章', 'L3', '部门规章'),
        'A09370304': ('司法解释', 'L7', '司法解释'),
        'A09370305': ('规范性文件', 'L3', '规范性文件'),
        'A09370306': ('政策文件', 'L3', '政策文件'),
    }

    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/2.0)',
            'Referer': 'https://www.cac.gov.cn',
        })

    def crawl_channel(self, channel_code: str, level_key: str,
                     name: str, level: str, reg_type: str,
                     lookback_days: int = 730) -> List[Dict]:
        """爬取单个 channel"""
        results = []
        page = 1
        cutoff_ts = (datetime.now().timestamp() - lookback_days * 86400) * 1000

        while page <= 50:
            try:
                params = {
                    'channelCode': channel_code,
                    'perPage': '20',
                    'pageno': str(page),
                    'condition': '0',
                    'fuhao': '=',
                    'value': '',
                }
                r = self.session.get(
                    'https://www.cac.gov.cn/cms/JsonList',
                    params=params, timeout=10
                )
                r.raise_for_status()
                data = r.json()
                items = data.get('list', [])
                if not items:
                    break

                for item in items:
                    pubtime = item.get('pubtime', '')
                    title = item.get('topic', '').strip()
                    infourl = item.get('infourl', '')
                    if not title or not infourl:
                        continue

                    # 日期过滤
                    if isinstance(pubtime, str) and pubtime:
                        try:
                            ts = datetime.strptime(pubtime.split('.')[0],
                                '%Y-%m-%d %H:%M:%S').timestamp()
                            if ts * 1000 < cutoff_ts:
                                return results
                        except:
                            pass

                    url = ('https:' + infourl) if infourl.startswith('//') else \
                          ('https://www.cac.gov.cn' + infourl) if infourl.startswith('/') else infourl

                    status = '现行有效'
                    if any(k in title for k in ['征求意见', '(征求意见稿)', '（征求意见稿）', '草案']):
                        status = '征求意见稿'

                    results.append({
                        'title': title,
                        'url': url,
                        'date': pubtime.split(' ')[0] if pubtime else '',
                        'level': level,
                        'type': reg_type,
                        'author': self._infer_author(title, level, channel_code),
                        'status': status,
                        'source': 'CAC',
                        'source_id': f'cac_{channel_code}',
                        'doc_number': self._extract_doc_number(title),
                    })

                page += 1
                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"  CAC page {page} failed: {e}")
                break

        return results

    def crawl(self, config: Dict, **kwargs) -> List[Dict]:
        """爬取所有配置的 CAC channels"""
        lookback_days = kwargs.get('lookback_days', 730)
        results = []
        for ch in config.get('channel_codes', []):
            code = ch['code']
            name, level, reg_type = self.CHANNEL_MAP.get(code, (ch['name'], ch['level'], ch.get('type', '部门规章')))
            # L1 (国家法律): 不过滤时间，获取全部历史
            # L2 (行政法规): 10年回查
            # 其他: lookback_days
            if level == 'L1':
                lb = 99999
            elif level == 'L2':
                lb = min(lookback_days, 3650)
            else:
                lb = lookback_days
            logger.info(f"  → CAC [{name}] channel={code} level={level}")
            items = self.crawl_channel(code, code, name, level, reg_type, lookback_days=lb)
            logger.info(f"    {len(items)} 条")
            results.extend(items)
        return results

    def _infer_author(self, title: str, level: str, channel: str) -> str:
        if level == 'L1': return '全国人大常委会'
        if level == 'L2': return '国务院'
        return '国家互联网信息办公室'

    def _extract_doc_number(self, title: str) -> str:
        m = re.search(r'[（\(〔【]\d{4}年?第?\d+号[）\〕】]', title)
        if m: return m.group(0)
        return ''


class SAMRCrawler:
    """SAMR 国家标准爬虫 - 已知可用"""

    KEYWORDS = ['数据安全', '网络安全', '个人信息', '信息安全', '人工智能',
                '密码', '等级保护', '身份认证']

    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/2.0)',
            'Accept': 'text/html',
        })
        self.base_url = config.get('base_url', 'http://openstd.samr.gov.cn/bzgk/std/')
        self.search_url = config.get('search_url', self.base_url + 'std_list')

    def crawl(self, config: Dict, **kwargs) -> List[Dict]:
        results = []
        lookback_days = kwargs.get('lookback_days', 730)

        for kw in self.KEYWORDS:
            try:
                items = self._search_keyword(kw, lookback_days)
                results.extend(items)
                logger.info(f"  SAMR [{kw}]: {len(items)} 条")
                time.sleep(1)
            except Exception as e:
                logger.warning(f"  SAMR [{kw}] failed: {e}")

        # 去重
        seen = set()
        unique = []
        for r in results:
            if r['title'] not in seen:
                seen.add(r['title'])
                unique.append(r)
        return unique

    def _search_keyword(self, keyword: str, lookback_days: int, max_pages: int = 2) -> List[Dict]:
        results = []
        for page in range(1, max_pages + 1):
            params = {
                'p.p1': '0', 'p.p90': 'circulation_date', 'p.p91': 'desc',
                'p.p2': keyword, 'page': str(page), 'pageSize': '20',
            }
            r = self.session.get(self.search_url, params=params, timeout=10)
            r.raise_for_status()
            items = self._parse_page(r.text)
            if not items:
                break
            results.extend(items)
        return results

    def _parse_page(self, html: str) -> List[Dict]:
        results = []
        positions = [(m.start(), m.group(1))
                     for m in re.finditer(r"showInfo\('([A-F0-9]+)'\)", html)]

        for i in range(0, len(positions) - 2, 3):
            if i + 2 >= len(positions):
                break

            p_title, hcno = positions[i + 1]
            snippet = html[p_title:p_title + 1000]

            # 标题
            title_m = re.search(r'showInfo\([\"\'].+?[\"\']\);">([^\<\r\n]+)', snippet)
            title = title_m.group(1).strip() if title_m else ''
            if not title:
                continue

            # 标准号
            p_std = positions[i][0]
            std_snippet = html[max(0, p_std - 200):p_std + 200]
            gb_m = re.search(r'(GB\s*4\d+[\d\-]+)', std_snippet)
            if not gb_m:
                gb_m = re.search(r'(GB/T?\s*[\d\.\-]+)', std_snippet)
            std_num = gb_m.group(1) if gb_m else ''

            # 日期
            date_m = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\.\d', snippet)
            date = date_m.group(1) if date_m else ''

            results.append({
                'title': re.sub(r'\s+', ' ', title),
                'url': f'{self.base_url}newGbInfo?hcno={hcno}',
                'date': date,
                'doc_number': std_num,
                'level': 'L4',
                'type': '国家标准',
                'author': '国家市场监督管理总局',
                'status': '现行有效',
                'source': 'SAMR',
                'source_id': 'samr_standards',
            })

        return results


class MinistryCrawler:
    """各部委 HTML 爬虫 - 待验证"""

    def __init__(self, config: Dict):
        self.config = config
        self.fetcher = BaseFetcher(config)

    def crawl(self, config: Dict, **kwargs) -> List[Dict]:
        """通用部委 HTML 爬虫"""
        results = []
        url = config.get('search_url') or config.get('base_url')

        logger.info(f"  → {config['name']} ({config['source_id']})")
        html = self.fetcher.fetch(url)
        if not html:
            logger.warning(f"    抓取失败")
            return results

        links = self._find_regulation_links(html, url)
        logger.info(f"    找到 {len(links)} 条链接")

        for link_url, title, date in links:
            results.append({
                'title': title,
                'url': link_url,
                'date': date or '',
                'level': config.get('levels', ['L3'])[0],
                'type': config.get('categories', ['部门规章'])[0],
                'author': self._extract_author(config),
                'status': self._infer_status(title),
                'source': config['name'],
                'source_id': config['source_id'],
                'doc_number': '',
            })

        return results

    def _find_regulation_links(self, html: str, base_url: str) -> List[tuple]:
        """从 HTML 中提取法规链接"""
        links = re.findall(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*?(?:法|条例|规定|'
            r'办法|规范|意见|通知|决定|批复)[^<]*)</a>',
            html[:300000], re.I
        )
        results = []
        seen = set()
        for href, text in links:
            text = text.strip()
            if len(text) < 5 or text in seen:
                continue
            seen.add(text)
            full_url = href if href.startswith('http') else \
                       (base_url.rstrip('/') + '/' + href.lstrip('/'))
            # 尝试从周围文本提取日期
            date = ''
            date_m = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
            if date_m:
                date = date_m.group(1).replace('年', '-').replace('月', '-').replace('/', '-')
            results.append((full_url, text, date))
        return results[:50]

    def _extract_author(self, config: Dict) -> str:
        name = config.get('name', '')
        author_map = {
            '工信部': '工业和信息化部', '央行': '中国人民银行',
            '公安部': '公安部', '卫健委': '国家卫生健康委员会',
            '交通部': '交通运输部', '教育部': '教育部',
            '市场监管总局': '国家市场监督管理总局',
        }
        for k, v in author_map.items():
            if k in name:
                return v
        return name

    def _infer_status(self, title: str) -> str:
        if any(k in title for k in ['征求意见', '草案', '(征求意见稿)']):
            return '征求意见稿'
        return '现行有效'


# ═══════════════════════════════════════════════════════════════════
# 爬虫注册表
# ═══════════════════════════════════════════════════════════════════

CRAWLERS = {
    'cac_api': CACSrawler,
    'samr_search': SAMRCrawler,
    'http_get': MinistryCrawler,
}


# ═══════════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════════

def crawl_source(source: Dict, **kwargs) -> List[Dict]:
    """并发执行单个来源"""
    method = source.get('method', 'http_get')
    crawler_cls = CRAWLERS.get(method, MinistryCrawler)
    try:
        crawler = crawler_cls(source)
        return crawler.crawl(source, **kwargs)
    except Exception as e:
        logger.error(f"[{source['source_id']}] Error: {e}")
        return []


def run_all_sources(levels: List[str] = None, source_ids: List[str] = None,
                   lookback_days: int = 730, concurrent: int = 5) -> List[Dict]:
    """并发运行所有指定来源"""
    cfg = Config(CONFIG_PATH)

    if source_ids:
        sources = [s for s in cfg.sources if s['source_id'] in source_ids]
    elif levels:
        sources = []
        for lv in levels:
            sources.extend(cfg.get_sources_by_level(lv))
        # 去重
        seen = set()
        unique = []
        for s in sources:
            if s['source_id'] not in seen:
                seen.add(s['source_id'])
                unique.append(s)
        sources = unique
    else:
        # 默认：已知可用的来源
        sources = cfg.get_working_sources()

    if not sources:
        logger.error("没有找到匹配的数据源")
        return []

    logger.info(f"=" * 60)
    logger.info(f"启动法规爬虫，并发数={concurrent}")
    logger.info(f"数据源: {[s['source_id'] for s in sources]}")
    logger.info(f"=" * 60)

    all_results = []
    with ThreadPoolExecutor(max_workers=concurrent) as executor:
        futures = {
            executor.submit(crawl_source, src, lookback_days=lookback_days): src
            for src in sources
        }
        for future in as_completed(futures):
            src = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                logger.info(f"  ✓ {src['source_id']}: {len(results)} 条")
            except Exception as e:
                logger.error(f"  ✗ {src['source_id']}: {e}")

    return all_results


def deduplicate(results: List[Dict]) -> List[Dict]:
    """按标题去重"""
    seen = set()
    unique = []
    for r in results:
        key = r['title']
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def field_normalize(record: Dict) -> Dict:
    """字段标准化"""
    level = record.get('level', 'L3')
    level_map = {
        'L1': 'L1-国家法律', 'L2': 'L2-行政法规',
        'L3': 'L3-部门/政府规章', 'L4': 'L4-国家标准',
        'L5': 'L5-行业标准', 'L6': 'L6-地方标准',
        'L7': 'L7-司法解释/规范性文件',
    }

    date_str = record.get('date', '')
    date_ts = 0
    if date_str:
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
            date_ts = int(dt.timestamp() * 1000)
        except:
            pass

    return {
        '法规标题': record.get('title', ''),
        '法规类型': record.get('type', '部门规章'),
        '来源层级': level_map.get(level, level),
        '发文机关': record.get('author', ''),
        '发布日期': date_ts,
        '状态': record.get('status', '现行有效'),
        '原文链接': record.get('url', ''),
        '标签': _infer_tags(record.get('title', '')),
        '_raw': record,  # 保留原始数据
    }


def _infer_tags(title: str) -> List[str]:
    tags = []
    kw_tags = {
        '数据安全': '数据安全', '网络安全': '网络安全',
        '个人信息': '个人信息', '人脸识别': '人脸识别',
        '算法': '算法推荐', '生成式AI': '生成式AI',
        '人工智能': '人工智能安全', '深度合成': '深度合成',
        '出境': '数据出境', '跨境': '数据跨境',
        '关键信息基础设施': '关键信息基础设施',
        '等级保护': '等级保护', '密码': '密码',
        '儿童': '儿童个人信息', '未成年': '未成年人网络保护',
        'App': 'App合规', '汽车': '汽车数据',
        '健康医疗': '健康医疗', '金融': '金融数据',
        '工业': '工业数据', '电信': '电信行业',
        '教育': '教育数据', '交通': '交通数据',
        '电商': '网络交易', '自动化决策': '自动化决策',
        '网络暴力': '网络暴力治理', '直播': '直播电商',
        '虚拟人': '数字虚拟人',
    }
    for kw, tag in kw_tags.items():
        if kw in title and tag not in tags:
            tags.append(tag)
    return tags


def main():
    parser = argparse.ArgumentParser(description='法规监控系统-并发爬虫引擎')
    parser.add_argument('--levels', '--levels', type=str, default='',
                       help='指定层级，如 L1,L2,L3,L4')
    parser.add_argument('--sources', type=str, default='',
                       help='指定来源ID，如 cac_l1,samr_standards')
    parser.add_argument('--all', action='store_true',
                       help='运行所有来源（包括未验证）')
    parser.add_argument('--concurrent', type=int, default=5,
                       help='并发数（默认5）')
    parser.add_argument('--lookback', type=int, default=730,
                       help='回查天数（默认730=2年）')
    parser.add_argument('--output', type=str, default='',
                       help='输出JSON路径（默认 data/YYYYMMDDHHMMSS_results.json）')
    args = parser.parse_args()

    # 解析参数
    levels = [l.strip() for l in args.levels.split(',') if l.strip()] if args.levels else None
    source_ids = [s.strip() for s in args.sources.split(',') if s.strip()] if args.sources else None

    if not levels and not source_ids and not args.all:
        # 默认运行已知可用的来源
        source_ids = ['cac_l1', 'cac_l2', 'cac_l3', 'cac_law_interp', 'samr_standards']

    results = run_all_sources(
        levels=levels,
        source_ids=source_ids,
        lookback_days=args.lookback,
        concurrent=args.concurrent
    )

    # 去重
    original_count = len(results)
    results = deduplicate(results)
    logger.info(f"\n去重: {original_count} → {len(results)} 条")

    # 按 level 统计
    by_level = {}
    for r in results:
        lv = r.get('level', '?')
        by_level[lv] = by_level.get(lv, 0) + 1
    for lv in sorted(by_level.keys()):
        logger.info(f"  {lv}: {by_level[lv]} 条")

    # 标准化字段
    normalized = [field_normalize(r) for r in results]

    # 输出
    if args.output:
        out_path = args.output
    else:
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(OUTPUT_DIR, f'{ts}_results.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(normalized),
            'summary': by_level,
            'records': normalized,
            'raw_records': results,
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已写入: {out_path}")
    logger.info(f"共 {len(normalized)} 条记录")
    return results


if __name__ == '__main__':
    main()
