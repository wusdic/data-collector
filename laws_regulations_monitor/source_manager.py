#!/usr/bin/env python3
"""
法律合规监控 - 数据源配置管理器
功能:
1. 加载和验证 data_sources.yaml 配置
2. 检查每个数据源与层级/库的匹配关系
3. 生成搜索查询
4. 支持动态更新数据源

使用方式:
    python source_manager.py --verify          # 验证配置
    python source_manager.py --list           # 列出所有数据源
    python source_manager.py --search L3      # 列出L3的所有数据源
    python source_manager.py --generate       # 生成搜索查询
"""

import os
import sys
import yaml
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

# ===== 配置路径 =====
CONFIG_FILE = os.path.join(
    os.path.dirname(__file__), 
    'data_sources.yaml'
)
BASE_DIR = os.path.expanduser('~/workspace/agent/workspace/data-collector/')


class SourceManager:
    """数据源配置管理器"""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def verify_all(self) -> Dict[str, Any]:
        """验证所有数据源配置"""
        results = {
            'total_sources': 0,
            'enabled_sources': 0,
            'issues': [],
            'by_level': {}
        }

        sources = self.config.get('sources', {})

        for level, level_config in sources.items():
            level_result = {
                'name': level_config.get('level_name', level),
                'priority': level_config.get('priority', 'unknown'),
                'total': 0,
                'enabled': 0,
                'sources': []
            }

            for src in level_config.get('sources', []):
                level_result['total'] += 1
                results['total_sources'] += 1
                
                if src.get('enabled', True):
                    level_result['enabled'] += 1
                    results['enabled_sources'] += 1

                src_issues = []
                # 检查必填字段
                if not src.get('url') and not src.get('account_id'):
                    src_issues.append("缺少 url 或 account_id")
                
                if not src.get('keywords'):
                    src_issues.append("未配置 keywords")
                
                if src_issues:
                    results['issues'].append(f"[{level}] {src.get('name', 'Unknown')}: {', '.join(src_issues)}")

                level_result['sources'].append({
                    'name': src.get('name', 'Unknown'),
                    'type': src.get('type', 'unknown'),
                    'enabled': src.get('enabled', True),
                    'issues': src_issues
                })

            results['by_level'][level] = level_result

        return results

    def list_sources(self, level: str = None) -> List[Dict]:
        """列出数据源"""
        sources = self.config.get('sources', {})
        results = []

        if level:
            if level in sources:
                level_config = sources[level]
                for src in level_config.get('sources', []):
                    results.append({
                        'level': level,
                        'level_name': level_config.get('level_name', level),
                        **src
                    })
        else:
            for lvl, level_config in sources.items():
                for src in level_config.get('sources', []):
                    results.append({
                        'level': lvl,
                        'level_name': level_config.get('level_name', lvl),
                        **src
                    })

        return results

    def generate_queries(self, limit: int = 50) -> List[Dict]:
        """生成搜索查询"""
        sources = self.list_sources()
        queries = []

        for src in sources:
            if not src.get('enabled', True):
                continue
            keywords = src.get('keywords', [])
            template = src.get('search_keyword_template', '{keyword}')

            for kw in keywords[:3]:  # 每个源最多3个关键词
                query = template.replace('{keyword}', kw)
                queries.append({
                    'level': src['level'],
                    'source': src['name'],
                    'query': query,
                    'url': src.get('url', ''),
                    'type': src.get('type', 'website'),
                })

                if len(queries) >= limit:
                    return queries

        return queries

    def update_source(self, level: str, source_name: str, updates: Dict) -> bool:
        """更新数据源配置"""
        sources = self.config.get('sources', {})
        if level not in sources:
            return False
        level_sources = sources[level].get('sources', [])
        for src in level_sources:
            if src.get('name') == source_name:
                src.update(updates)
                self._save_config()
                return True
        return False

    def add_source(self, level: str, source: Dict) -> bool:
        """添加数据源"""
        sources = self.config.get('sources', {})
        if level not in sources:
            sources[level] = {
                'level_name': level,
                'law_type': level,
                'priority': 'medium',
                'sources': []
            }
        sources[level].setdefault('sources', []).append(source)
        self._save_config()
        return True

    def remove_source(self, level: str, source_name: str) -> bool:
        """删除数据源"""
        sources = self.config.get('sources', {})
        if level not in sources:
            return False
        level_sources = sources[level].get('sources', [])
        for i, src in enumerate(level_sources):
            if src.get('name') == source_name:
                del level_sources[i]
                self._save_config()
                return True
        return False

    def enable_disable_source(self, level: str, source_name: str, enabled: bool) -> bool:
        """启用/禁用数据源"""
        return self.update_source(level, source_name, {'enabled': enabled})

    def get_stats(self) -> Dict:
        """获取统计信息"""
        sources = self.config.get('sources', {})
        stats = {
            'total_levels': len(sources),
            'total_sources': 0,
            'enabled_sources': 0,
            'by_level': {},
            'by_type': {}
        }

        for level, level_config in sources.items():
            level_sources = level_config.get('sources', [])
            enabled = sum(1 for s in level_sources if s.get('enabled', True))
            stats['total_sources'] += len(level_sources)
            stats['enabled_sources'] += enabled
            stats['by_level'][level] = {
                'name': level_config.get('level_name', level),
                'total': len(level_sources),
                'enabled': enabled,
                'priority': level_config.get('priority', 'unknown')
            }

            for src in level_sources:
                src_type = src.get('type', 'unknown')
                if src_type not in stats['by_type']:
                    stats['by_type'][src_type] = 0
                stats['by_type'][src_type] += 1

        return stats

    def print_verification_report(self, results: Dict):
        """打印验证报告"""
        print("\n" + "=" * 70)
        print("📋 数据源配置验证报告")
        print("=" * 70)
        print(f"\n总计: {results['total_sources']} 个数据源")
        print(f"启用: {results['enabled_sources']} 个")
        print(f"问题: {len(results['issues'])} 个")

        if results['issues']:
            print("\n🔴 问题:")
            for issue in results['issues'][:20]:
                print(f"  • {issue}")
            if len(results['issues']) > 20:
                print(f"  ... 还有 {len(results['issues']) - 20} 个问题")

        print("\n📊 按层级统计:")
        print("-" * 70)
        print(f"{'层级':<20} {'名称':<22} {'数据源':<8} {'启用':<8} {'优先级'}")
        print("-" * 70)

        for level, data in results['by_level'].items():
            print(f"{level:<20} {data['name']:<22} {data['total']:<8} {data['enabled']:<8} {data['priority']}")

        print("=" * 70)

    def print_source_list(self, sources: List[Dict]):
        """打印数据源列表"""
        print("\n" + "=" * 80)
        print("📋 数据源列表")
        print("=" * 80)

        current_level = None
        for src in sources:
            if src['level'] != current_level:
                current_level = src['level']
                print(f"\n### {src['level']} - {src['level_name']}")
                print("-" * 80)

            status = "✅" if src.get('enabled', True) else "❌"
            print(f"{status} [{src['type']}] {src['name']}")
            print(f"    URL: {src.get('url', 'N/A')}")
            if src.get('keywords'):
                kws = src['keywords'][:5]
                print(f"    关键词: {', '.join(kws)}")

        print("=" * 80)

    def print_stats(self, stats: Dict):
        """打印统计信息"""
        print("\n📊 统计信息")
        print("-" * 50)
        print(f"层级数: {stats['total_levels']}")
        print(f"数据源总数: {stats['total_sources']}")
        print(f"启用数量: {stats['enabled_sources']}")
        print(f"\n按层级:")
        for level, data in stats['by_level'].items():
            print(f"  {level}: {data['enabled']}/{data['total']} ({data['priority']})")
        print(f"\n按类型: {stats['by_type']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='法律合规数据源配置管理器')
    parser.add_argument('--verify', '-v', action='store_true', help='验证配置')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有数据源')
    parser.add_argument('--search', '-s', metavar='LEVEL', help='列出指定层级的数据源')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    parser.add_argument('--generate', '-g', action='store_true', help='生成搜索查询')
    parser.add_argument('--enable', nargs=3, metavar=('LEVEL', 'NAME', 'BOOL'),
                       help='启用/禁用数据源')
    parser.add_argument('--add', '-a', nargs=2, metavar=('LEVEL', 'NAME'),
                       help='添加数据源')
    parser.add_argument('--remove', '-r', nargs=2, metavar=('LEVEL', 'NAME'),
                       help='删除数据源')

    args = parser.parse_args()

    try:
        manager = SourceManager()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 验证
    if args.verify:
        results = manager.verify_all()
        manager.print_verification_report(results)
        return

    # 统计
    if args.stats:
        stats = manager.get_stats()
        manager.print_stats(stats)
        return

    # 列表
    if args.list:
        sources = manager.list_sources()
        manager.print_source_list(sources)
        return

    # 指定层级列表
    if args.search:
        sources = manager.list_sources(level=args.search)
        if sources:
            manager.print_source_list(sources)
        else:
            print(f"未找到层级 {args.search} 的数据源")
        return

    # 生成查询
    if args.generate:
        queries = manager.generate_queries(limit=20)
        print("\n🔍 生成的搜索查询 (前20个):")
        print("-" * 80)
        for q in queries:
            print(f"[{q['level']}] {q['source']}")
            print(f"  {q['query']}")
            print()
        return

    # 启用/禁用
    if args.enable:
        level, name, enabled = args.enable
        success = manager.enable_disable_source(level, name, enabled.lower() == 'true')
        if success:
            print(f"✅ 已{'启用' if enabled.lower() == 'true' else '禁用'} {level}/{name}")
        else:
            print(f"❌ 未找到 {level}/{name}")
        return

    # 默认：显示帮助
    parser.print_help()


if __name__ == '__main__':
    main()
