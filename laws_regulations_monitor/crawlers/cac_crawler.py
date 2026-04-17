"""
网信办爬虫 - 修复版
使用 /cms/JsonList API 直接获取数据

Channel codes:
  A09370301 - 法律
  A09370302 - 行政法规
  A09370303 - 部门规章
  A09370304 - 司法解释
  A09370305 - 规范性文件
  A09370306 - 政策文件
  A09370307 - 政策解读
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class CACCrawler(BaseCrawler):
    """网信办官网爬虫 - 使用 JSON API"""

    # 按层级分类的 channel codes
    CHANNEL_CODES = {
        'L1': {'name': '法律', 'code': 'A09370301'},
        'L2': {'name': '行政法规', 'code': 'A09370302'},
        'L3': {'name': '部门规章', 'code': 'A09370303'},
        'L4司法': {'name': '司法解释', 'code': 'A09370304'},
        'L3规范': {'name': '规范性文件', 'code': 'A09370305'},
        'L3政策': {'name': '政策文件', 'code': 'A09370306'},
        '解读': {'name': '政策解读', 'code': 'A09370307'},
    }

    def __init__(self, config: Dict[str, Any], lookback_days: int = 90):
        super().__init__(config, lookback_days)
        self.base_url = config.get('base_url', 'https://www.cac.gov.cn')
        self.api_url = f"{self.base_url}/cms/JsonList"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/1.0)',
            'Referer': self.base_url,
        })

    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """
        爬取网信办所有分类数据
        """
        results = []

        # 对每个 channel 爬取所有页面
        for level_key, channel_info in self.CHANNEL_CODES.items():
            code = channel_info['code']
            name = channel_info['name']
            logger.info(f"正在抓取 CAC [{name}] (channel: {code})")

            items = self._crawl_channel(code, level_key)
            logger.info(f"  → 获取 {len(items)} 条记录")
            results.extend(items)

        return self._deduplicate(results)

    def _crawl_channel(self, channel_code: str, level_key: str, 
                       max_pages: int = 50) -> List[Dict[str, Any]]:
        """
        爬取单个 channel 的所有页面
        """
        results = []
        page = 1
        total_pages = max_pages  # 先设一个上限

        while page <= total_pages:
            try:
                items, total = self._fetch_page(channel_code, page)
                if not items:
                    break

                # 从第一条记录推断总页数
                if total and total > 0:
                    # total 可能是总记录数，计算页数
                    per_page = 20
                    total_pages = min((total + per_page - 1) // per_page, max_pages)

                for item in items:
                    processed = self._process_item(item, level_key)
                    if processed:
                        results.append(processed)

                if page >= total_pages:
                    break

                page += 1
                self._rate_limit()

            except Exception as e:
                logger.warning(f"  CAC channel {channel_code} page {page} 失败: {e}")
                break

        return results

    def _fetch_page(self, channel_code: str, page_num: int) -> tuple:
        """
        获取单页数据
        Returns: (items, total_count)
        """
        params = {
            'channelCode': channel_code,
            'perPage': '20',
            'pageno': str(page_num),
            'condition': '0',
            'fuhao': '=',
            'value': '',
        }

        resp = self.session.get(self.api_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        items = data.get('list', [])
        total = data.get('total', 0)

        return items, total

    def _process_item(self, item: Dict, level_key: str) -> Optional[Dict[str, Any]]:
        """
        处理单条记录
        """
        title = item.get('topic', '').strip()
        pubtime = item.get('pubtime', '')
        infourl = item.get('infourl', '')

        if not title or not infourl:
            return None

        # 过滤政策解读（不是法规本身）
        if level_key == '解读':
            return None

        # 提取日期
        if isinstance(pubtime, str) and pubtime:
            date_str = pubtime.split(' ')[0]
            try:
                pub_date = datetime.strptime(date_str, '%Y-%m-%d')
                if (datetime.now() - pub_date).days > self.lookback_days * 2:
                    return None  # 太旧的跳过
            except:
                date_str = ''
        else:
            date_str = ''

        # 规范化 URL
        if infourl.startswith('//'):
            url = f'https:{infourl}'
        elif infourl.startswith('/'):
            url = f'{self.base_url}{infourl}'
        else:
            url = infourl

        # 判断法规类型
        reg_type = self._infer_regulation_type(title, level_key)

        # 判断状态
        status = self._infer_status(title)

        return {
            'title': title,
            'url': url,
            'date': date_str,
            'level': level_key,
            'reg_type': reg_type,
            'author': '国家互联网信息办公室',
            'status': status,
            'doc_number': self._extract_doc_number(title),
        }

    def _infer_regulation_type(self, title: str, level_key: str) -> str:
        """根据标题推断法规类型"""
        if level_key in ('L1', 'L2'):
            return '国家法律' if level_key == 'L1' else '行政法规'

        type_keywords = {
            '办法': '部门规章',
            '规定': '部门规章',
            '条例': '行政法规',
            '细则': '部门规章',
            '规范': '规范性文件',
            '制度': '规范性文件',
            '决定': '部门规章',
            '意见': '规范性文件',
            '通知': '规范性文件',
        }

        for kw, t in type_keywords.items():
            if kw in title:
                return t
        return '部门规章'

    def _infer_status(self, title: str) -> str:
        """判断法规状态"""
        if '征求意见' in title or '（征求意见稿）' in title or '(征求意见稿)' in title:
            return '征求意见稿'
        if '（草案）' in title or '(草案)' in title:
            return '草案'
        return '现行有效'

    def _extract_doc_number(self, title: str) -> str:
        """从标题提取文号"""
        patterns = [
            r'（\d{4}年第\d+号）',
            r'\(\d{4}年第\d+号\)',
            r'〔\d{4}〕\d+号',
            r'【\d+号】',
        ]
        for p in patterns:
            m = re.search(p, title)
            if m:
                return m.group(0)
        return ''

    def _deduplicate(self, results: List[Dict]) -> List[Dict[str, Any]]:
        """根据标题去重"""
        seen = set()
        unique = []
        for r in results:
            key = r['title']
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique
