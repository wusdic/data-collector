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
    ref_参考资料库/
  regulations.csv

配置: 从 data_sources.yaml 加载 7层+2库 的搜索源
"""

import os
import sys
import json
import csv
import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# ===== 配置路径 =====
BASE_DIR = os.path.expanduser('~/workspace/agent/workspace/data-collector/regulations')
CSV_FILE = os.path.join(os.path.dirname(BASE_DIR), 'regulations.csv')
LOG_DIR = os.path.join(os.path.dirname(BASE_DIR), 'logs')
CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), 'laws_regulations_monitor', 'data_sources.yaml'
)

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(LOG_DIR, f'monitor_{datetime.now().strftime("%Y%m%d")}.log'),
            encoding='utf-8'
        ),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('law_monitor')


# ===== 层级缩写映射 =====
LEVEL_KEY_MAP = {
    'L1_国家法律': 'L1',
    'L2_行政法规': 'L2',
    'L3_部门文件': 'L3',
    'L4_国家标准': 'L4',
    'L5_行业标准': 'L5',
    'L6_地方文件': 'L6',
    'L7_地方标准': 'L7',
    '执法案例库': 'case',
    '参考资料库': 'ref',
}


def load_data_sources(config_path: str = None) -> Dict[str, Any]:
    """从 data_sources.yaml 加载配置"""
    import yaml
    path = config_path or CONFIG_FILE
    if not os.path.exists(path):
        logger.error(f"配置文件不存在: {path}")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def build_search_queries(data_sources: Dict) -> Dict[str, Dict]:
    """
    从 data_sources.yaml 构建 SEARCH_QUERIES 格式
    返回: { level_short: { name, dir, queries, sources } }
    """
    result = {}
    sources = data_sources.get('sources', {})
    monitor_config = data_sources.get('monitor_config', {})
    local_paths = monitor_config.get('local_paths', {})
    level_dirs = local_paths.get('level_dirs', {})

    for level_key, level_config in sources.items():
        short = LEVEL_KEY_MAP.get(level_key, level_key)

        # 构建搜索查询列表
        queries = []
        level_sources = []
        for src in level_config.get('sources', []):
            if not src.get('enabled', True):
                continue

            level_sources.append(src)

            template = src.get('search_keyword_template', '{keyword}')
            keywords = src.get('keywords', [])

            # 每个源取前2个关键词生成查询
            for kw in keywords[:2]:
                query = template.replace('{keyword}', kw)
                # 添加时间范围
                year_current = datetime.now().year
                year_prev = year_current - 1
                if str(year_current) not in query and str(year_prev) not in query:
                    query += f" {year_prev} {year_current}"
                queries.append(query)

        # 目录名
        dir_name = level_dirs.get(short, level_config.get('level_name', level_key))

        result[short] = {
            'name': level_config.get('level_name', level_key),
            'dir': dir_name,
            'queries': queries[:6],  # 每层最多6条查询
            'sources': level_sources,
            'priority': level_config.get('priority', 'medium'),
        }

    return result


class LawMonitor:
    """法律法规监控器 - 从 data_sources.yaml 加载配置"""

    def __init__(self, config_path: str = None):
        self.base_dir = BASE_DIR
        self.state_file = os.path.join(os.path.dirname(BASE_DIR), '.monitor_state.json')
        self.state = self._load_state()
        self.seen_urls = set(self.state.get('seen_urls', []))
        self.seen_titles = set(self.state.get('seen_titles', []))

        # 从配置文件加载搜索配置
        self.data_sources = load_data_sources(config_path)
        self.search_config = build_search_queries(self.data_sources)
        self.monitor_config = self.data_sources.get('monitor_config', {})

        logger.info(f"已加载 {len(self.search_config)} 个层级的搜索配置")

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
        if level in self.search_config:
            return os.path.join(self.base_dir, self.search_config[level]['dir'])
        return self.base_dir

    def _build_filename(self, level: str, title: str, date: str) -> str:
        """构建文件名: L3_法规名称_2025-06-27.txt"""
        dir_name = self.search_config.get(level, {}).get('name', level)
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
                content = self._extract_text_from_html(content)
                return content[:10000] if content else None
        except Exception as e:
            logger.warning(f"下载失败 {url}: {e}")
            return None

    def _extract_text_from_html(self, html: str) -> str:
        """从HTML提取纯文本"""
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', html)
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

    def get_search_queries(self, levels: List[str] = None) -> Dict[str, List[str]]:
        """获取搜索查询（供外部 Agent 调用 web_search 时使用）"""
        if levels is None:
            levels = list(self.search_config.keys())

        result = {}
        for level in levels:
            if level in self.search_config:
                result[level] = self.search_config[level]['queries']
        return result

    def get_sources_info(self, levels: List[str] = None) -> List[Dict]:
        """获取数据源信息"""
        if levels is None:
            levels = list(self.search_config.keys())

        result = []
        for level in levels:
            if level in self.search_config:
                config = self.search_config[level]
                for src in config.get('sources', []):
                    result.append({
                        'level': level,
                        'level_name': config['name'],
                        'source_name': src.get('name', ''),
                        'url': src.get('url', ''),
                        'type': src.get('type', ''),
                        'enabled': src.get('enabled', True),
                    })
        return result

    def save_results(self, results: List[Dict], download: bool = True) -> Dict:
        """
        保存搜索结果（由 Agent 调用 web_search 后传入结果）

        每条 result 应包含: level, title, url, snippet, date(可选)
        """
        new_records = []

        for item in results:
            level = item.get('level', '')
            title = item.get('title', '')
            url = item.get('url', '')

            if not title or level not in self.search_config:
                continue

            if self._is_seen(url, title):
                continue

            date = item.get('date') or self._extract_date(
                item.get('snippet', '') + title
            )

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
                    logger.info(f"  ✓ 保存: {filename}")

            # 写入CSV
            record = self._write_record(level, {**item, 'date': date}, content, filepath)
            new_records.append(record)
            self._mark_seen(url, title)

        if new_records:
            self._append_to_csv(new_records)

        self._save_state()

        return {
            'total_new': len(new_records),
            'records': new_records,
            'csv_file': CSV_FILE,
        }

    def verify_config(self) -> Dict[str, Any]:
        """验证数据源配置的匹配关系"""
        results = {
            'total_sources': 0,
            'enabled_sources': 0,
            'issues': [],
            'by_level': {}
        }

        sources = self.data_sources.get('sources', {})

        # 每个层级应该匹配的发文机关/关键词
        level_expected = {
            'L1_国家法律': {
                'keywords': ['全国人大', '人大常委会', '法律', '主席令'],
                'wrong_keywords': ['部门规章', '国家标准', '地方标准', '行业标准'],
            },
            'L2_行政法规': {
                'keywords': ['国务院', '国务院令', '行政法规'],
                'wrong_keywords': ['国家标准', '地方标准', '部门规章'],
            },
            'L3_部门文件': {
                'keywords': ['网信办', '工信部', '公安部', '央行', '市场监管', '卫健委',
                            '交通部', '教育部', '部门规章', '规范性文件'],
                'wrong_keywords': ['国家标准 GB', '地方标准 DB', '行政法规'],
            },
            'L4_国家标准': {
                'keywords': ['国家标准', 'GB/T', 'GB ', '标准委', 'TC260', 'SAC'],
                'wrong_keywords': ['地方标准 DB', '行政法规', '部门规章'],
            },
            'L5_行业标准': {
                'keywords': ['金融行业', '电信行业', '卫生行业', '行业标准', 'JR', 'YD'],
                'wrong_keywords': ['国家标准 GB/T', '地方标准 DB', '行政法规'],
            },
            'L6_地方文件': {
                'keywords': ['省', '市', '自治区', '地方性法规', '地方政府规章'],
                'wrong_keywords': ['国家标准 GB', '行业标准', '部门规章'],
            },
            'L7_地方标准': {
                'keywords': ['地方标准', 'DB', '省市监局', '市场监督管理局'],
                'wrong_keywords': ['国家标准 GB/T', '行业标准 JR', '行政法规'],
            },
            '执法案例库': {
                'keywords': ['行政处罚', '执法案例', '通报', '罚款', '违法'],
                'wrong_keywords': ['国家标准', '地方标准'],
            },
            '参考资料库': {
                'keywords': ['指南', '白皮书', '研究报告', '最佳实践'],
                'wrong_keywords': ['行政处罚', '国家标准 GB'],
            },
        }

        for level_key, level_config in sources.items():
            level_result = {
                'name': level_config.get('level_name', level_key),
                'priority': level_config.get('priority', 'unknown'),
                'total': 0,
                'enabled': 0,
                'mismatch': [],
                'ok': [],
            }

            expected = level_expected.get(level_key, {})

            for src in level_config.get('sources', []):
                level_result['total'] += 1
                results['total_sources'] += 1

                if src.get('enabled', True):
                    level_result['enabled'] += 1
                    results['enabled_sources'] += 1

                # 验证匹配关系
                src_name = src.get('name', '')
                src_url = src.get('url', '')
                src_keywords = src.get('keywords', [])
                check_pattern = src.get('check_pattern', '')

                mismatch_reasons = []

                # 检查URL和源名称是否包含错误层级的标识
                combined = f"{src_name} {src_url} {' '.join(src_keywords)} {check_pattern}"
                for wrong in expected.get('wrong_keywords', []):
                    if wrong in combined:
                        mismatch_reasons.append(f"可能包含'{wrong}'（不属于本层级）")

                # 检查是否包含本层级应有的标识
                has_match = False
                for ok_kw in expected.get('keywords', []):
                    if ok_kw in combined:
                        has_match = True
                        break

                if mismatch_reasons:
                    for reason in mismatch_reasons:
                        results['issues'].append(
                            f"[{level_config.get('level_name', level_key)}] {src_name}: {reason}"
                        )
                    level_result['mismatch'].append({
                        'source': src_name,
                        'reasons': mismatch_reasons
                    })
                elif has_match:
                    level_result['ok'].append(src_name)
                else:
                    # 无明显匹配也无明显错误，标记为待确认
                    level_result['ok'].append(f"{src_name} (待确认)")

            results['by_level'][level_key] = level_result

        return results

    def print_verification(self, results: Dict):
        """打印验证报告"""
        print("\n" + "=" * 70)
        print("📋 数据源配置验证报告")
        print("=" * 70)
        print(f"\n总计: {results['total_sources']} 个数据源")
        print(f"启用: {results['enabled_sources']} 个")
        print(f"问题: {len(results['issues'])} 个")

        if results['issues']:
            print("\n🔴 匹配问题:")
            for issue in results['issues']:
                print(f"  • {issue}")

        print("\n📊 按层级统计:")
        print("-" * 70)
        for level, data in results['by_level'].items():
            status = "✅" if not data['mismatch'] else "⚠️"
            print(f"{status} {data['name']:<22} {data['enabled']}/{data['total']} 启用 "
                  f"({data['priority']})")
            if data['mismatch']:
                for m in data['mismatch']:
                    print(f"    🔴 {m['source']}: {', '.join(m['reasons'])}")
            if data['ok']:
                for ok in data['ok'][:5]:
                    print(f"    ✅ {ok}")

        print("=" * 70)

    def run(self, levels: List[str] = None) -> Dict:
        """
        执行监控 - 输出搜索查询供 Agent 使用

        实际搜索由 Agent 的 web_search 工具完成，
        本方法返回需要搜索的查询列表。
        """
        logger.info("=" * 60)
        logger.info("法律法规监控 - 生成搜索任务")
        logger.info("=" * 60)

        if levels is None:
            levels = list(self.search_config.keys())

        queries_by_level = self.get_search_queries(levels)

        total_queries = sum(len(qs) for qs in queries_by_level.values())
        logger.info(f"共 {len(queries_by_level)} 个层级, {total_queries} 条搜索查询")

        for level, queries in queries_by_level.items():
            level_name = self.search_config[level]['name']
            logger.info(f"\n[{level}] {level_name} - {len(queries)} 条查询:")
            for q in queries:
                logger.info(f"  • {q}")

        return {
            'queries_by_level': queries_by_level,
            'total_queries': total_queries,
            'levels': list(queries_by_level.keys()),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='法律法规监控')
    parser.add_argument('--levels', '-l', nargs='+',
                        choices=list(LEVEL_KEY_MAP.values()),
                        help='指定监控层级')
    parser.add_argument('--verify', '-v', action='store_true',
                        help='验证数据源配置')
    parser.add_argument('--queries', '-q', action='store_true',
                        help='输出搜索查询')
    parser.add_argument('--sources', '-s', action='store_true',
                        help='列出数据源')
    parser.add_argument('--config', '-c', default=None,
                        help='指定配置文件路径')
    args = parser.parse_args()

    monitor = LawMonitor(args.config)
    levels = args.levels if args.levels else None

    if args.verify:
        results = monitor.verify_config()
        monitor.print_verification(results)
        return

    if args.queries:
        result = monitor.run(levels)
        for level, queries in result['queries_by_level'].items():
            name = monitor.search_config[level]['name']
            print(f"\n[{level}] {name}:")
            for q in queries:
                print(f"  {q}")
        return

    if args.sources:
        sources = monitor.get_sources_info(levels)
        current_level = None
        for src in sources:
            if src['level'] != current_level:
                current_level = src['level']
                print(f"\n### [{src['level']}] {src['level_name']}")
                print("-" * 60)
            status = "✅" if src['enabled'] else "❌"
            print(f"  {status} [{src['type']}] {src['source_name']}")
            print(f"      URL: {src['url']}")
        return

    # 默认: 输出搜索查询
    result = monitor.run(levels)
    print(f"\n📋 共 {result['total_queries']} 条搜索查询，覆盖 {len(result['levels'])} 个层级")
    print("使用 --verify 验证配置，--sources 列出数据源，--queries 查看查询详情")


if __name__ == '__main__':
    main()
