"""
配置驱动的通用爬虫引擎
Engine不认识任何层级，只认配置

核心设计：
- 读 config/registry.yaml 获取所有层级列表
- 遍历 config/levels/*.yaml，按配置执行爬取
- 支持 json_api, html_api, html, spa 四种爬虫类型
- 通用去重（标题+日期）
- 支持 lookback_days 和 keywords 参数
"""

import os
import re
import sys
import json
import time
import logging
import hashlib
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob
from typing import List, Dict, Any, Optional

import yaml
import requests

# Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from engine.base_crawler import BaseCrawler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(BASE_DIR, 'logs', 'crawler_engine.log'),
            mode='a', encoding='utf-8'
        )
    ]
)
logger = logging.getLogger('engine')


# ═══════════════════════════════════════════════════════════════════
# 通用 HTTP Fetcher
# ═══════════════════════════════════════════════════════════════════

class HttpFetcher:
    """HTTP fetcher with encoding detection and retry"""

    def __init__(self, config: Dict):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/2.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        extra = config.get('headers', {})
        if isinstance(extra, dict):
            self.session.headers.update(extra)

        self.timeout = config.get('timeout', 15)
        self.retry = config.get('retry', 3)
        self.encoding_order = config.get('encoding_order', ['utf-8', 'gbk', 'gb2312', 'gb18030'])
        self.rate_limit = config.get('rate_limit', 1.0)

    def fetch(self, url: str) -> Optional[str]:
        for attempt in range(self.retry):
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                r.raise_for_status()

                # 自动检测编码
                for enc in self.encoding_order:
                    try:
                        r.encoding = enc
                        _ = r.text[:500]
                        break
                    except Exception:
                        continue

                return r.text
            except Exception as e:
                if attempt == self.retry - 1:
                    logger.warning(f"  Fetch failed: {url[:60]} - {e}")
                time.sleep(1)
        return None

    def rate_limit_sleep(self):
        time.sleep(self.rate_limit)


# ═══════════════════════════════════════════════════════════════════
# JSON API 爬虫（用于 CAC）
# ═══════════════════════════════════════════════════════════════════

class JsonApiCrawler(BaseCrawler):
    """
    JSON API 爬虫
    用于: CAC 的 JSON API 接口
    """

    CHANNEL_MAP = {
        'A09370301': ('法律', 'L1', '国家法律'),
        'A09370302': ('行政法规', 'L2', '行政法规'),
        'A09370303': ('部门规章', 'L3', '部门规章'),
        'A09370304': ('司法解释', 'L7', '司法解释'),
        'A09370305': ('规范性文件', 'L3', '规范性文件'),
        'A09370306': ('政策文件', 'L3', '政策文件'),
    }

    def crawl(self, config: Dict, **kwargs) -> List[Dict[str, Any]]:
        lookback_days = kwargs.get('lookback_days', config.get('lookback_days', 730))
        results = []

        # 获取 channel 列表
        channel_codes = config.get('channel_codes', [])
        if not channel_codes and config.get('channel_code'):
            channel_codes = [{'code': config['channel_code']}]

        for ch in channel_codes:
            code = ch['code']
            name, level, reg_type = self.CHANNEL_MAP.get(
                code, (ch.get('name', config['name']), config.get('level', 'L3'), config.get('reg_type', '部门规章'))
            )
            logger.info(f"  → [{config['name']}] channel={code} level={level}")
            items = self._crawl_channel(config, code, name, level, reg_type, lookback_days)
            logger.info(f"    {len(items)} 条")
            results.extend(items)
            self._rate_limit()

        return results

    def _crawl_channel(self, config: Dict, channel_code: str,
                       name: str, level: str, reg_type: str,
                       lookback_days: int) -> List[Dict[str, Any]]:
        results = []
        page = 1
        cutoff_ts = (datetime.now().timestamp() - lookback_days * 86400) * 1000
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/2.0)',
            'Referer': 'https://www.cac.gov.cn',
        })

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
                r = session.get(
                    config.get('api_url', 'https://www.cac.gov.cn/cms/JsonList'),
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
                    if pubtime:
                        try:
                            ts = datetime.strptime(pubtime.split('.')[0],
                                '%Y-%m-%d %H:%M:%S').timestamp()
                            if ts * 1000 < cutoff_ts:
                                return results
                        except Exception:
                            pass

                    url = infourl
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = 'https://www.cac.gov.cn' + url

                    results.append({
                        'title': title,
                        'url': url,
                        'date': pubtime.split(' ')[0] if pubtime else '',
                        'level': level,
                        'type': reg_type,
                        'author': config.get('author', self._infer_author(title, level)),
                        'status': self.infer_status(title),
                        'source': config.get('name', 'CAC'),
                        'source_id': config.get('source_id', ''),
                        'doc_number': self.extract_doc_number(title),
                    })

                page += 1
                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"  CAC page {page} failed: {e}")
                break

        return results

    def _infer_author(self, title: str, level: str) -> str:
        if level == 'L1':
            return '全国人大常委会'
        if level == 'L2':
            return '国务院'
        return '国家互联网信息办公室'


# ═══════════════════════════════════════════════════════════════════
# HTML API 爬虫（用于 SAMR 国家标准搜索）
# ═══════════════════════════════════════════════════════════════════

class HtmlApiCrawler(BaseCrawler):
    """
    HTML API 爬虫
    用于: SAMR 国家标准搜索等
    """

    def crawl(self, config: Dict, **kwargs) -> List[Dict[str, Any]]:
        lookback_days = kwargs.get('lookback_days', config.get('lookback_days', 730))
        keywords = kwargs.get('keywords', config.get('keywords', []))
        if not keywords:
            keywords = ['数据安全', '网络安全', '个人信息', '信息安全',
                        '人工智能', '密码', '等级保护']

        results = []
        fetcher = HttpFetcher(config)

        for kw in keywords:
            logger.info(f"  → [{config['name']}] keyword={kw}")
            items = self._search_keyword(fetcher, config, kw, lookback_days)
            logger.info(f"    {len(items)} 条")
            results.extend(items)
            time.sleep(1)

        # 去重
        return self.deduplicate(results)

    def _search_keyword(self, fetcher: HttpFetcher, config: Dict,
                        keyword: str, lookback_days: int,
                        max_pages: int = 2) -> List[Dict[str, Any]]:
        results = []
        base_url = config.get('search_url', config.get('base_url', ''))
        search_url = config.get('search_url', base_url)

        for page in range(1, max_pages + 1):
            params = {
                'p.p1': '0',
                'p.p90': 'circulation_date',
                'p.p91': 'desc',
                'p.p2': keyword,
                'page': str(page),
                'pageSize': '20',
            }
            import requests as req
            r = req.get(search_url, params=params, timeout=10)
            r.raise_for_status()
            items = self._parse_page(r.text, config)
            if not items:
                break
            results.extend(items)

        # 日期过滤
        cutoff = (datetime.now() - datetime.timedelta(days=lookback_days)).timestamp()
        filtered = []
        for item in results:
            date_str = item.get('date', '')
            if date_str:
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    if dt.timestamp() >= cutoff:
                        filtered.append(item)
                except Exception:
                    filtered.append(item)
            else:
                filtered.append(item)
        return filtered

    def _parse_page(self, html: str, config: Dict) -> List[Dict[str, Any]]:
        results = []
        positions = [(m.start(), m.group(1))
                     for m in re.finditer(r"showInfo\('([A-F0-9]+)'\)", html)]

        for i in range(0, len(positions) - 2, 3):
            if i + 2 >= len(positions):
                break

            p_title, hcno = positions[i + 1]
            snippet = html[p_title:p_title + 1000]

            title_m = re.search(r'showInfo\(["\'].+?["\']\);">([^<\r\n]+)', snippet)
            title = title_m.group(1).strip() if title_m else ''
            if not title:
                continue

            p_std = positions[i][0]
            std_snippet = html[max(0, p_std - 200):p_std + 200]
            gb_m = re.search(r'(GB\s*\d+[\d\-]+)', std_snippet)
            if not gb_m:
                gb_m = re.search(r'(GB/T?\s*[\d\.\-]+)', std_snippet)
            std_num = gb_m.group(1) if gb_m else ''

            date_m = re.search(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\.\d', snippet)
            date = date_m.group(1) if date_m else ''

            results.append({
                'title': re.sub(r'\s+', ' ', title),
                'url': f"{config.get('base_url', 'http://openstd.samr.gov.cn/bzgk/std/')}newGbInfo?hcno={hcno}",
                'date': date,
                'doc_number': std_num,
                'level': config.get('level', 'L4'),
                'type': config.get('reg_type', '国家标准'),
                'author': config.get('author', '国家市场监督管理总局'),
                'status': self.infer_status(title),
                'source': config.get('name', 'SAMR'),
                'source_id': config.get('source_id', 'samr_standards'),
            })

        return results


# ═══════════════════════════════════════════════════════════════════
# 通用 HTML 爬虫
# ═══════════════════════════════════════════════════════════════════

class HtmlCrawler(BaseCrawler):
    """
    通用 HTML 爬虫
    用于: 传统服务端渲染的部委/政府网站
    """

    def crawl(self, config: Dict, **kwargs) -> List[Dict[str, Any]]:
        lookback_days = kwargs.get('lookback_days', config.get('lookback_days', 730))
        fetcher = HttpFetcher(config)
        results = []

        url = config.get('search_url') or config.get('base_url')
        logger.info(f"  → [{config['name']}] {url[:60]}")

        html = fetcher.fetch(url)
        if not html:
            logger.warning(f"    抓取失败")
            return results

        links = self._find_regulation_links(html, url)
        logger.info(f"    找到 {len(links)} 条链接")

        for link_url, title, date in links:
            # 日期过滤
            if date and not self.is_recent(date):
                continue
            if not self.matches_keywords(title):
                continue

            results.append({
                'title': title,
                'url': link_url,
                'date': date,
                'level': config.get('level', 'L3'),
                'type': config.get('reg_type', '部门规章'),
                'author': config.get('author', self.infer_author(link_url)),
                'status': self.infer_status(title),
                'source': config.get('name', ''),
                'source_id': config.get('source_id', ''),
                'doc_number': self.extract_doc_number(title),
            })

        return self.deduplicate(results)

    def _find_regulation_links(self, html: str, base_url: str) -> List[tuple]:
        """从 HTML 中提取法规链接"""
        links = re.findall(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]*?(?:'
            r'法|条例|规定|办法|规范|意见|通知|决定|批复|公告|标准)'
            r'[^<]*)</a>',
            html[:300000], re.I
        )
        results = []
        seen = set()
        for href, text in links:
            text = text.strip()
            if len(text) < 5 or text in seen:
                continue
            seen.add(text)
            full_url = self.normalize_url(href, base_url)
            if not full_url:
                continue
            date = self.extract_date(text) or ''
            results.append((full_url, text, date))
        return results[:50]


# ═══════════════════════════════════════════════════════════════════
# SPA 爬虫（占位，需要浏览器渲染）
# ═══════════════════════════════════════════════════════════════════

class SpaCrawler(BaseCrawler):
    """
    SPA 爬虫（当前环境不可用，仅占位）
    用于: 纯客户端渲染的网站，如全国人大法规库
    """

    def crawl(self, config: Dict, **kwargs) -> List[Dict[str, Any]]:
        logger.warning(f"  [{config['name']}] SPA类型暂不支持（需要浏览器渲染）")
        return []


# ═══════════════════════════════════════════════════════════════════
# 爬虫类型注册表
# ═══════════════════════════════════════════════════════════════════

CRAWLER_TYPES = {
    'json_api': JsonApiCrawler,
    'html_api': HtmlApiCrawler,
    'html': HtmlCrawler,
    'spa': SpaCrawler,
}


# ═══════════════════════════════════════════════════════════════════
# 通用去重（标题+日期）
# ═══════════════════════════════════════════════════════════════════

def generic_dedup(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """通用去重：基于 title + date"""
    seen = set()
    unique = []
    for r in results:
        key = (r.get('title', '').strip(), r.get('date', '').strip())
        if key[0] and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ═══════════════════════════════════════════════════════════════════
# 配置驱动的爬虫引擎
# ═══════════════════════════════════════════════════════════════════

class ConfigDrivenCrawlerEngine:
    """
    配置驱动的通用爬虫引擎

    设计原则：
    - 引擎不认识任何层级，只认配置
    - 读 config/registry.yaml 获取所有层级列表
    - 遍历 config/levels/*.yaml，按配置执行爬取

    用法：
        engine = ConfigDrivenCrawlerEngine('config/registry.yaml')
        results = engine.run_all(lookback_days=730)
        results = engine.run_level('L3')
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(registry_path)))
        self.registry = self._load_registry()
        self.levels_dir = os.path.join(self.base_dir, 'config', 'levels')

    def _load_registry(self) -> Dict[str, Any]:
        """加载注册表"""
        with open(self.registry_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _load_level_config(self, level_code: str) -> Optional[Dict[str, Any]]:
        """加载单个层级配置"""
        path = os.path.join(self.levels_dir, f'{level_code}.yaml')
        if not os.path.exists(path):
            logger.warning(f"  层级配置不存在: {path}")
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _create_crawler(self, source: Dict[str, Any]) -> Optional[BaseCrawler]:
        """根据 source type 创建爬虫实例"""
        crawler_type = source.get('type', 'html')
        cls = CRAWLER_TYPES.get(crawler_type)
        if cls is None:
            logger.warning(f"  未知爬虫类型: {crawler_type}")
            return None
        return cls(source)

    # ─── 核心接口 ───────────────────────────────────────────

    def run_all(self, lookback_days: int = None,
                level_codes: List[str] = None,
                concurrent: int = 5) -> Dict[str, Any]:
        """
        运行所有层级（或指定层级）

        Args:
            lookback_days: 回查天数（覆盖配置默认值）
            level_codes: 指定层级列表（如 ['L1','L2']），None=全部
            concurrent: 并发数

        Returns:
            {
                'total': int,           # 总记录数
                'by_level': dict,        # 按层级统计
                'records': list,         # 所有记录
                'errors': list,          # 错误信息
            }
        """
        index = self.registry.get('levels_index', {})
        all_records = []
        errors = []
        by_level = {}

        targets = []
        for code, info in index.items():
            if level_codes and code not in level_codes:
                continue
            targets.append((code, info))

        logger.info("=" * 60)
        logger.info(f"启动配置驱动爬虫引擎")
        logger.info(f"目标层级: {[t[0] for t in targets]}")
        logger.info(f"并发数: {concurrent}")
        logger.info("=" * 60)

        for code, info in targets:
            try:
                level_results = self.run_level(code, lookback_days=lookback_days)
                by_level[code] = len(level_results)
                all_records.extend(level_results)
            except Exception as e:
                errors.append({'level': code, 'error': str(e)})
                logger.error(f"  [{code}] 层级执行失败: {e}")

        # 通用去重
        original_count = len(all_records)
        all_records = generic_dedup(all_records)
        dedup_count = original_count - len(all_records)

        logger.info(f"\n去重: {original_count} → {len(all_records)} 条（去除 {dedup_count} 条）")

        return {
            'total': len(all_records),
            'by_level': by_level,
            'records': all_records,
            'errors': errors,
            'dedup_count': dedup_count,
        }

    def run_level(self, level_code: str, lookback_days: int = None) -> List[Dict[str, Any]]:
        """
        运行单个层级

        Args:
            level_code: 层级代码，如 'L1', 'L3'
            lookback_days: 回查天数

        Returns:
            该层级的所有爬取结果
        """
        config = self._load_level_config(level_code)
        if not config:
            return []

        lb = lookback_days if lookback_days is not None else config.get('lookback_days', 730)
        sources = config.get('sources', [])
        level_results = []

        logger.info(f"\n══ {level_code}: {config.get('name', '')} ══")
        logger.info(f"  回查天数: {lb}")
        logger.info(f"  来源数: {len(sources)}")

        for source in sources:
            try:
                items = self.crawl_source(source, lookback_days=lb)
                level_results.extend(items)
                logger.info(f"  ✓ [{source['source_id']}] {len(items)} 条")
            except Exception as e:
                logger.error(f"  ✗ [{source['source_id']}] {e}")

        return level_results

    def crawl_source(self, source: Dict[str, Any],
                     lookback_days: int = None,
                     keywords: List[str] = None) -> List[Dict[str, Any]]:
        """
        爬取单个数据源

        Args:
            source: 数据源配置字典
            lookback_days: 回查天数
            keywords: 关键词列表（覆盖配置）

        Returns:
            爬取结果列表
        """
        crawler = self._create_crawler(source)
        if crawler is None:
            return []

        kwargs = {}
        if lookback_days is not None:
            kwargs['lookback_days'] = lookback_days
        if keywords:
            kwargs['keywords'] = keywords

        try:
            return crawler.crawl(source, **kwargs)
        except Exception as e:
            logger.error(f"  [{source.get('source_id', '?')}] crawl error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════════

def run(levels: List[str] = None,
        lookback_days: int = 730,
        concurrent: int = 5,
        output: str = None) -> Dict[str, Any]:
    """便捷运行入口"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    registry_path = os.path.join(base_dir, 'config', 'registry.yaml')

    engine = ConfigDrivenCrawlerEngine(registry_path)
    result = engine.run_all(
        lookback_days=lookback_days,
        level_codes=levels,
        concurrent=concurrent,
    )

    # 输出
    if output:
        out_path = output
    else:
        os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        out_path = os.path.join(base_dir, 'data', f'{ts}_results.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"\n结果已写入: {out_path}")
    logger.info(f"共 {result['total']} 条记录")

    for lv, cnt in sorted(result.get('by_level', {}).items()):
        logger.info(f"  {lv}: {cnt} 条")

    return result


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='配置驱动爬虫引擎')
    parser.add_argument('--levels', type=str, default='',
                       help='指定层级，如 L1,L2,L3（空=全部）')
    parser.add_argument('--lookback', type=int, default=730,
                       help='回查天数（默认730）')
    parser.add_argument('--concurrent', type=int, default=5,
                       help='并发数（默认5）')
    parser.add_argument('--output', type=str, default='',
                       help='输出JSON路径')
    args = parser.parse_args()

    levels = [l.strip() for l in args.levels.split(',') if l.strip()] if args.levels else None

    run(levels=levels,
        lookback_days=args.lookback,
        concurrent=args.concurrent,
        output=args.output or None)
