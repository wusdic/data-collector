#!/usr/bin/env python3
"""
法律法规监控 - 主程序
输出: CSV + 原文txt文件

命名规则: {层级}_{法规名称}_{发布时间}.txt
目录结构:
  regulations/
    L1_国家法律/
    L2_行政法规/
    L3_部门文件/
    L4_国家标准/
    L5_行业标准/
    L6_地方文件/
    L7_地方标准/
    cases_执法案例库/
  regulations.csv
"""

import os
import sys
import json
import csv
import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

# ===== 配置 =====
BASE_DIR = os.path.expanduser('~/workspace/agent/workspace/data-collector/regulations')
CSV_FILE = os.path.join(os.path.dirname(BASE_DIR), 'regulations.csv')
LOG_FILE = os.path.join(os.path.dirname(BASE_DIR), 'logs', f'monitor_{datetime.now().strftime("%Y%m%d")}.log')

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('law_monitor')


# ===== 7层+2库搜索配置 =====
SEARCH_QUERIES = {
    'L1': {
        'name': 'L1-国家法律',
        'dir': 'L1_国家法律',
        'queries': [
            'site:flk.npc.gov.cn 法律 2024 2025',
            '全国人大常委会 最新法律 2025',
        ],
    },
    'L2': {
        'name': 'L2-行政法规',
        'dir': 'L2_行政法规',
        'queries': [
            'site:gov.cn 行政法规 数据安全 2025',
            '国务院 最新条例 2025',
        ],
    },
    'L3': {
        'name': 'L3-部门文件',
        'dir': 'L3_部门文件',
        'queries': [
            'site:cac.gov.cn 部门规章 2025',
            'site:miit.gov.cn 部门规章 2025',
            '网信办 最新办法 规定 2025',
        ],
    },
    'L4': {
        'name': 'L4-国家标准',
        'dir': 'L4_国家标准',
        'queries': [
            'site:openstd.samr.gov.cn 国家标准 2025',
            'GB/T 最新发布 数据安全 2025',
        ],
    },
    'L5': {
        'name': 'L5-行业标准',
        'dir': 'L5_行业标准',
        'queries': [
            '金融行业标准 最新 2025',
            '电信行业标准 最新 2025',
        ],
    },
    'L6': {
        'name': 'L6-地方文件',
        'dir': 'L6_地方文件',
        'queries': [
            '省市 数据安全 地方性法规 2025',
        ],
    },
    'L7': {
        'name': 'L7-地方标准',
        'dir': 'L7_地方标准',
        'queries': [
            '地方标准 数据安全 DB 2025',
        ],
    },
    'case': {
        'name': '执法案例库',
        'dir': 'cases_执法案例库',
        'queries': [
            'site:cac.gov.cn 行政处罚 2025',
            '数据安全 行政处罚 通报 2025',
        ],
    },
}


class LawMonitor:
    """法律法规监控器"""

    def __init__(self):
        self.base_dir = BASE_DIR
        self.state_file = os.path.join(os.path.dirname(BASE_DIR), '.monitor_state.json')
        self.state = self._load_state()
        self.seen_urls = set(self.state.get('seen_urls', []))
        self.seen_titles = set(self.state.get('seen_titles', []))

    def _load_state(self) -> Dict:
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'seen_urls': [], 'seen_titles': [], 'last_run': None}

    def _save_state(self):
        self.state['last_run'] = datetime.now().isoformat()
        self.state['seen_urls'] = list(self.seen_urls)[-1000:]
        self.state['seen_titles'] = list(self.seen_titles)[-500:]
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _normalize_title(self, title: str) -> str:
        """标准化标题用于比对"""
        t = re.sub(r'[\[【\(（].*?[\]】\)）]', '', title)
        return t.strip().lower()

    def _is_seen(self, url: str, title: str) -> bool:
        return url in self.seen_urls or self._normalize_title(title) in self.seen_titles

    def _mark_seen(self, url: str, title: str):
        if url:
            self.seen_urls.add(url)
        self.seen_titles.add(self._normalize_title(title))

    def _search(self, level: str, queries: List[str]) -> List[Dict]:
        """使用 web_search 搜索"""
        results = []
        for q in queries[:2]:
            try:
                from search_tool import search  # 假设有这个工具
            except:
                pass
            
            # 通过 subprocess 调用 openclaw search
            import subprocess
            cmd = ['openclaw', 'search', '--query', q, '--limit', '20']
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if r.returncode == 0:
                try:
                    data = json.loads(r.stdout)
                    for item in data.get('results', []):
                        results.append({
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'snippet': item.get('snippet', ''),
                            'level': level,
                        })
                except:
                    pass
        return results

    def _extract_date(self, text: str) -> Optional[str]:
        patterns = [
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                d = m.group(1)
                return d.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-')
        return None

    def _sanitize_filename(self, name: str) -> str:
        """清理非法文件名字符"""
        return re.sub(r'[<>:"/\\|?*]', '_', name)[:80]

    def _get_level_dir(self, level: str) -> str:
        if level in SEARCH_QUERIES:
            return os.path.join(self.base_dir, SEARCH_QUERIES[level]['dir'])
        return self.base_dir

    def _build_filename(self, level: str, title: str, date: str) -> str:
        """构建文件名: L3_法规名称_2025-06-27.txt"""
        dir_name = SEARCH_QUERIES.get(level, {}).get('name', level)
        safe_title = self._sanitize_filename(title)
        date_part = f"_{date}" if date else ""
        return f"{dir_name}_{safe_title}{date_part}.txt"

    def _download_content(self, url: str) -> Optional[str]:
        """下载页面内容"""
        if not url:
            return None
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8', errors='replace')
                # 提取正文
                content = self._extract_text_from_html(content)
                return content[:10000] if content else None  # 限制长度
        except Exception as e:
            logger.warning(f"下载失败 {url}: {e}")
            return None

    def _extract_text_from_html(self, html: str) -> str:
        """从HTML提取纯文本"""
        # 移除脚本和样式
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        # 移除标签
        text = re.sub(r'<[^>]+>', ' ', html)
        # 清理空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _write_record(self, level: str, item: Dict, content: Optional[str], filepath: str) -> Dict:
        """写入CSV记录"""
        return {
            'level': level,
            'title': item['title'],
            'date': item.get('date', ''),
            'url': item['url'],
            'filepath': filepath,
            'has_content': content is not None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

    def _append_to_csv(self, records: List[Dict]):
        """追加到CSV文件"""
        fieldnames = ['level', 'title', 'date', 'url', 'filepath', 'has_content', 'timestamp']
        file_exists = os.path.exists(CSV_FILE)
        
        with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for rec in records:
                writer.writerow(rec)

    def run(self, levels: List[str] = None, download: bool = True) -> Dict:
        """执行监控"""
        logger.info("=" * 60)
        logger.info("开始法律法规监控")
        logger.info("=" * 60)

        if levels is None:
            levels = list(SEARCH_QUERIES.keys())

        all_new = []

        for level in levels:
            if level not in SEARCH_QUERIES:
                continue
            
            config = SEARCH_QUERIES[level]
            logger.info(f"\n>>> {config['name']}")
            
            # 1. 搜索
            items = []
            for q in config['queries'][:2]:
                logger.info(f"    搜索: {q}")
                # 这里通过 Agent 的 web_search 工具搜索
                # 结果由调用者传入
                items.extend(self._mock_search_results(level, q))
            
            logger.info(f"    找到 {len(items)} 条")
            
            # 2. 去重 + 下载
            new_records = []
            for item in items:
                title = item.get('title', '')
                url = item.get('url', '')
                
                if self._is_seen(url, title):
                    continue
                
                date = item.get('date') or self._extract_date(item.get('snippet', '') + title)
                item['date'] = date
                
                # 生成文件路径
                filename = self._build_filename(level, title, date)
                dir_path = self._get_level_dir(level)
                os.makedirs(dir_path, exist_ok=True)
                filepath = os.path.join(dir_path, filename)
                
                # 下载内容
                content = None
                if download and url:
                    content = self._download_content(url)
                    if content:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(f"标题: {title}\n")
                            f.write(f"链接: {url}\n")
                            f.write(f"日期: {date}\n")
                            f.write(f"层级: {level}\n")
                            f.write(f"\n{'='*60}\n\n")
                            f.write(content)
                        logger.info(f"    ✓ 保存: {filename}")
                
                # 写入CSV
                record = self._write_record(level, item, content, filepath)
                new_records.append(record)
                
                # 标记已处理
                self._mark_seen(url, title)
            
            if new_records:
                self._append_to_csv(new_records)
                all_new.extend(new_records)
                logger.info(f"    新增 {len(new_records)} 条")

        self._save_state()
        
        logger.info("=" * 60)
        logger.info(f"完成! 新增 {len(all_new)} 条")
        logger.info(f"CSV: {CSV_FILE}")
        logger.info("=" * 60)

        return {
            'total_new': len(all_new),
            'records': all_new,
            'csv_file': CSV_FILE,
        }

    def _mock_search_results(self, level: str, query: str) -> List[Dict]:
        """占位 - 实际由 Agent 的 web_search 工具提供"""
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description='法律法规监控')
    parser.add_argument('--levels', '-l', nargs='+',
                        choices=['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case'])
    parser.add_argument('--nodownload', action='store_true')
    args = parser.parse_args()

    monitor = LawMonitor()
    levels = args.levels if args.levels else None
    result = monitor.run(levels=levels, download=not args.nodownload)
    
    print(f"\n{'✅' if result['total_new'] == 0 else '📋'} 新增 {result['total_new']} 条")
    if result['total_new'] > 0:
        print(f"CSV: {result['csv_file']}")


if __name__ == '__main__':
    main()
