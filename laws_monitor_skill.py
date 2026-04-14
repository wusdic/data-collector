#!/usr/bin/env python3
"""
OpenClaw Agent Skill: 法律合规数据库监控
基于 OpenClaw 内置工具（web_search + feishu_*）实现，无需爬虫

触发方式:
  1. 定时: 通过 cron job 调用
  2. 手动: 用户发指令"检查新法规"

工作流程:
  1. 搜索最新法规动态 (web_search)
  2. 对比飞书多维表格现有记录 (feishu_bitable_*)
  3. 补全新记录 (feishu_bitable_*)
  4. 通知用户 (message)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# ===== 日志配置 =====
LOG_DIR = os.path.expanduser('~/workspace/agent/workspace/data-collector/logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f'law_monitor_{datetime.now().strftime("%Y%m%d")}.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('law_monitor')


# ===== 7层+2库 搜索关键词配置 =====
SEARCH_QUERIES = {
    'L1': {
        'name': 'L1-国家法律',
        'queries': [
            'site:flk.npc.gov.cn 2024 2025 数据安全 网络安全 法律',
            '全国人大常委会 最新法律 2024 2025',
        ],
    },
    'L2': {
        'name': 'L2-行政法规',
        'queries': [
            'site:gov.cn 行政法规 数据安全 2024 2025',
            '国务院 最新条例 2024 2025',
        ],
    },
    'L3': {
        'name': 'L3-部门文件',
        'queries': [
            'site:cac.gov.cn 部门规章 2024 2025',
            '网信办 最新办法 规定 2024 2025',
            '工信部 部门规章 最新 2024 2025',
        ],
    },
    'L4': {
        'name': 'L4-国家标准',
        'queries': [
            'site:openstd.samr.gov.cn 国家标准 2024 2025',
            'GB/T 最新发布 2024 2025 数据安全',
        ],
    },
    'L5': {
        'name': 'L5-行业标准',
        'queries': [
            '金融行业标准 最新 2024 2025',
            '电信行业标准 最新 2024 2025',
            '医疗行业标准 最新 2024 2025',
        ],
    },
    'L6': {
        'name': 'L6-地方文件',
        'queries': [
            '省市 数据安全 地方性法规 最新 2024 2025',
            '地方ZF 最新规定 数据管理 2024 2025',
        ],
    },
    'L7': {
        'name': 'L7-地方标准',
        'queries': [
            '地方标准 数据安全 DB 最新 2024 2025',
            '省市监局 地方标准 发布 2024 2025',
        ],
    },
    'case': {
        'name': '执法案例库',
        'queries': [
            'site:cac.gov.cn 行政处罚 执法案例 2024 2025',
            '数据安全 个人信息 行政处罚 通报 2024 2025',
            'App违规 违法收集 处罚 2024 2025',
        ],
    },
}


class LawMonitor:
    """法律合规数据库监控器"""

    BITABLE_APP_TOKEN = 'GLupbdKK7aCApgsxO7NcFIGbnJf'
    BITABLE_TABLES = {
        'main': 'tblUkUwxCDBWKDdK',  # 法规主表
        'cases': 'tbljSjhjzu1LtQwX',  # 执法案例库
    }

    # 飞书多维表格字段映射
    MAIN_TABLE_FIELDS = {
        'title': '法规标题',
        'type': '法规类型',
        'level': '来源层级',
        'author': '发文机关',
        'doc_number': '文号',
        'publish_date': '发布日期',
        'effective_date': '生效日期',
        'status': '状态',
        'source_url': '原文链接',
        'local_path': '全文存储路径',
        'tags': '标签',
    }

    CASE_TABLE_FIELDS = {
        'title': '案例标题',
        'case_type': '案例类型',
        'authority': '处罚/审理机关',
        'case_date': '案例日期',
        'related_laws': '涉及法规',
        'summary': '案情摘要',
        'key_points': '认定要点',
        'result': '处罚结果',
        'source_url': '原文链接',
    }

    def __init__(self, lookback_days: int = 30):
        self.lookback_days = lookback_days
        self.state_file = os.path.join(LOG_DIR, 'monitor_state.json')
        self.state = self._load_state()

    # ===== 状态管理 =====
    def _load_state(self) -> Dict:
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_run': None, 'seen_titles': {}, 'stats': {}}

    def _save_state(self):
        self.state['last_run'] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _is_seen(self, level: str, title: str) -> bool:
        """检查是否已处理过"""
        titles = self.state.get('seen_titles', {}).get(level, [])
        return title in titles

    def _mark_seen(self, level: str, title: str):
        if level not in self.state['seen_titles']:
            self.state['seen_titles'][level] = []
        if title not in self.state['seen_titles'][level]:
            self.state['seen_titles'][level].append(title)
            # 保留最近500条
            if len(self.state['seen_titles'][level]) > 500:
                self.state['seen_titles'][level] = self.state['seen_titles'][level][-500:]

    # ===== 飞书操作 =====
    def get_existing_titles(self, table_id: str) -> set:
        """获取飞书表格中已有的标题列表"""
        import subprocess
        result = subprocess.run([
            sys.executable, '-c', f'''
import sys
sys.path.insert(0, '/home/gem/workspace/agent/extensions/openclaw-lark/skills/feishu-bitable/SKILL.md')
'''
        ], capture_output=True, text=True)

        # 使用 OpenClaw CLI
        result = subprocess.run(
            ['openclaw', 'feishu', 'bitable', 'records', 'list',
             '--app', self.BITABLE_APP_TOKEN,
             '--table', table_id,
             '--page-size', '500'],
            capture_output=True, text=True, timeout=30
        )

        titles = set()
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                for rec in data.get('data', {}).get('items', []):
                    fields = rec.get('fields', {})
                    # 尝试提取标题
                    title = fields.get('法规标题', fields.get('案例标题', ''))
                    if isinstance(title, list):
                        title = title[0].get('text', '') if title else ''
                    if title:
                        titles.add(self._normalize(title))
            except:
                pass

        logger.info(f"从飞书表格 {table_id} 加载 {len(titles)} 条已有标题")
        return titles

    def _normalize(self, text: str) -> str:
        """标准化文本用于比对"""
        import re
        text = re.sub(r'[\[【\(（].*?[\]】\)）]', '', text)
        return text.strip().lower()

    def add_record(self, table_id: str, fields: Dict) -> bool:
        """添加记录到飞书多维表格"""
        import subprocess
        import shlex

        # 将 fields 转换为 JSON
        fields_json = json.dumps(fields, ensure_ascii=False)

        cmd = [
            'openclaw', 'feishu', 'bitable', 'record', 'create',
            '--app', self.BITABLE_APP_TOKEN,
            '--table', table_id,
            '--fields', fields_json
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            logger.info(f"✓ 成功添加记录: {fields.get('法规标题', fields.get('案例标题', '?'))}")
            return True
        else:
            logger.warning(f"✗ 添加记录失败: {result.stderr[:200]}")
            return False

    # ===== 搜索 =====
    def search_regulations(self, level: str, queries: List[str]) -> List[Dict]:
        """使用 web_search 搜索法规"""
        results = []
        seen = set()

        for query in queries[:3]:  # 每层最多3个查询
            try:
                import subprocess
                result = subprocess.run(
                    ['openclaw', 'search', '--query', query, '--limit', '20'],
                    capture_output=True, text=True, timeout=60
                )

                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for item in data.get('results', []):
                        title = item.get('title', '')
                        url = item.get('url', '')
                        snippet = item.get('snippet', '')

                        if not title or title in seen:
                            continue
                        seen.add(title)

                        # 提取日期
                        date = self._extract_date(snippet + title)

                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet,
                            'date': date,
                            'level': level,
                        })

                logger.info(f"[{level}] 搜索 '{query}': 获得 {len(results)} 条")
            except Exception as e:
                logger.error(f"搜索失败 [{level}][{query}]: {e}")

        return results

    def _extract_date(self, text: str) -> Optional[str]:
        """从文本提取日期"""
        import re
        patterns = [
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        return None

    def _is_recent(self, date_str: str) -> bool:
        """检查日期是否在回查范围内"""
        if not date_str:
            return True
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                cutoff = datetime.now() - timedelta(days=self.lookback_days)
                return dt >= cutoff
            except ValueError:
                continue
        return True

    # ===== 主流程 =====
    def run(self, levels: List[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """执行监控扫描"""
        logger.info("=" * 60)
        logger.info("开始法律合规数据库监控扫描")
        logger.info(f"回查范围: {self.lookback_days} 天")
        logger.info("=" * 60)

        if levels is None:
            levels = list(SEARCH_QUERIES.keys())

        all_results = {}
        total_new = 0

        for level in levels:
            if level not in SEARCH_QUERIES:
                continue

            config = SEARCH_QUERIES[level]
            logger.info(f"\n>>> 检查 {config['name']} ...")

            # 1. 搜索
            items = self.search_regulations(level, config['queries'])
            logger.info(f"    搜索到 {len(items)} 条")

            # 2. 过滤（去重 + 日期过滤）
            new_items = []
            for item in items:
                title = item['title']
                if self._is_seen(level, title):
                    continue
                if not self._is_recent(item.get('date', '')):
                    continue

                new_items.append(item)
                self._mark_seen(level, title)

            logger.info(f"    新增 {len(new_items)} 条")

            if new_items and not dry_run:
                # 3. 写入飞书
                table_id = self.BITABLE_TABLES['cases'] if level == 'case' else self.BITABLE_TABLES['main']
                added = 0
                for item in new_items[:50]:  # 每次最多处理50条
                    fields = self._build_fields(level, item)
                    if fields and self.add_record(table_id, fields):
                        added += 1

                logger.info(f"    写入飞书 {added} 条")
                all_results[level] = {'new': len(new_items), 'added': added}
                total_new += added
            else:
                all_results[level] = {'new': len(new_items), 'added': 0}

        # 保存状态
        self._save_state()

        # 4. 生成报告
        report = self._build_report(all_results)

        logger.info("=" * 60)
        logger.info(f"扫描完成! 新增 {total_new} 条")
        logger.info("=" * 60)

        return {
            'results': all_results,
            'report': report,
            'total_new': total_new,
            'timestamp': datetime.now().isoformat(),
        }

    def _build_fields(self, level: str, item: Dict) -> Optional[Dict]:
        """构建飞书记录字段"""
        title = item['title']
        url = item['url']
        date_str = item.get('date', '')
        snippet = item.get('snippet', '')

        # 解析日期为时间戳
        publish_ts = None
        if date_str:
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    publish_ts = int(dt.timestamp() * 1000)
                    break
                except ValueError:
                    continue

        if level == 'case':
            # 执法案例库
            return {
                '案例标题': title,
                '原文链接': {'link': url, 'text': url} if url else None,
                '案例日期': publish_ts,
                '案情摘要': snippet[:500] if snippet else None,
            }
        else:
            # 法规主表
            type_options = {
                'L1': '法律', 'L2': '行政法规', 'L3': '部门规章',
                'L4': '国家标准', 'L5': '行业标准', 'L6': '地方政府规章', 'L7': '地方性法规'
            }
            level_options = {
                'L1': 'L1-国家法律', 'L2': 'L2-行政法规', 'L3': 'L3-部门/政府规章',
                'L4': 'L4-国家标准', 'L5': 'L5-行业标准', 'L6': 'L6-地方文件', 'L7': 'L7-地方标准'
            }

            return {
                '法规标题': title,
                '法规类型': type_options.get(level, '规范性文件'),
                '来源层级': level_options.get(level, level),
                '原文链接': {'link': url, 'text': url} if url else None,
                '发布日期': publish_ts,
                '状态': '现行有效',
            }

    def _build_report(self, results: Dict) -> str:
        """构建文字报告"""
        level_names = {
            'L1': 'L1-国家法律', 'L2': 'L2-行政法规', 'L3': 'L3-部门文件',
            'L4': 'L4-国家标准', 'L5': 'L5-行业标准', 'L6': 'L6-地方文件',
            'L7': 'L7-地方标准', 'case': '执法案例库'
        }

        lines = [
            "📋 **法律合规数据库监控报告**",
            "",
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        total_new = 0
        has_new = False

        for level, data in results.items():
            n = data['new']
            a = data['added']
            total_new += n
            if n > 0:
                has_new = True
                lines.append(f"**{level_names.get(level, level)}**")
                lines.append(f"  发现 {n} 条新内容，写入 {a} 条")

        if not has_new:
            lines.append("✅ 本次扫描未发现新增法规")
        else:
            lines.append(f"**汇总**: 新增 {total_new} 条")

        lines.append("")
        lines.append("> 🤖 自动监控")

        return '\n'.join(lines)


# ===== CLI =====
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='法律合规数据库监控')
    parser.add_argument('--levels', '-l', nargs='+',
                        choices=['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case'],
                        default=None, help='指定层级')
    parser.add_argument('--days', '-d', type=int, default=30,
                        help='回查天数 (默认30)')
    parser.add_argument('--dry', action='store_true',
                        help='仅搜索，不写入飞书')
    parser.add_argument('--report', '-r', action='store_true',
                        help='输出报告')

    args = parser.parse_args()

    monitor = LawMonitor(lookback_days=args.days)
    result = monitor.run(levels=args.levels, dry_run=args.dry)

    if args.report:
        print(result['report'])
    else:
        total = result['total_new']
        print(f"{'✅' if total == 0 else '📋'} 扫描完成! 新增 {total} 条")
