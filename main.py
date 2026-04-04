#!/usr/bin/env python3
"""
DataCollector - 自动化资料收集与管理系统
========================================

Usage:
    python main.py <command> [options]

Commands:
    search      搜索资料
    download    下载资源
    collect     一站式收集（搜索+下载+分类）
    monitor     启动更新监控
    serve       启动 API 服务
    stats       查看统计信息
    init        初始化项目
"""

import sys
import argparse
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from data_collector.config.config_loader import get_config
from data_collector.core.search.engine import SearchEngine
from data_collector.core.downloader.download_manager import DownloadManager
from data_collector.core.classifier.classifier import Classifier
from data_collector.core.updater.update_monitor import UpdateMonitor
from data_collector.storage.database.db_manager import DatabaseManager
from data_collector.storage.file_manager.file_manager import FileManager
from data_collector.api.api_server import APIServer
from data_collector.utils.logger import setup_logging


class DataCollectorCLI:
    """命令行工具"""
    
    def __init__(self, config_path: str = None):
        self.config = get_config(config_path)
        self._init_components()
    
    def _init_components(self):
        """初始化组件"""
        self.search_engine = SearchEngine(self.config.get('SEARCH', {}))
        self.download_manager = DownloadManager(self.config.get('DOWNLOAD', {}))
        self.classifier = Classifier(self.config.get('CLASSIFIER', {}))
        self.updater = UpdateMonitor(self.config.get('UPDATER', {}))
        self.db_manager = DatabaseManager(self.config.get('DATABASE', {}))
        self.file_manager = FileManager()
    
    def search(self, query: str, engines: list = None, max_results: int = 20):
        """搜索资料"""
        print(f"\n🔍 搜索: {query}")
        print("-" * 50)
        
        results = self.search_engine.search(
            query=query,
            engines=engines,
            max_results=max_results
        )
        
        print(f"找到 {len(results)} 条结果:\n")
        
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get('title', '')}")
            print(f"   来源: {result.get('source', '')}")
            print(f"   链接: {result.get('url', '')}")
            print(f"   摘要: {result.get('snippet', '')[:100]}...")
            print()
        
        return results
    
    def download(self, urls: list, filenames: list = None):
        """下载资源"""
        print(f"\n📥 开始下载 {len(urls)} 个文件...")
        print("-" * 50)
        
        results = self.download_manager.download_batch(
            urls=urls,
            filenames=filenames
        )
        
        success = sum(1 for r in results if r)
        print(f"\n✅ 下载完成: {success}/{len(urls)}")
        
        for path in results:
            if path:
                print(f"   - {path}")
        
        return results
    
    def collect(self, query: str, max_results: int = 10, auto_classify: bool = True):
        """
        一站式收集
        搜索 -> 下载 -> 分类 -> 存储
        """
        print(f"\n🚀 开始收集资料: {query}")
        print("=" * 60)
        
        # 1. 搜索
        print("\n[1/4] 🔍 搜索资料...")
        results = self.search_engine.search(query=query, max_results=max_results)
        print(f"找到 {len(results)} 条结果")
        
        if not results:
            print("❌ 未找到相关资料")
            return
        
        # 2. 分类
        print("\n[2/4] 🏷️ 分类处理...")
        classified = []
        for result in results:
            classification = self.classifier.classify(
                title=result.get('title', ''),
                content=result.get('snippet', ''),
                url=result.get('url', '')
            )
            result['classification'] = classification
            classified.append(result)
            print(f"   - {result['title'][:40]}... → {classification.get('primary_category', '未分类')}")
        
        # 3. 下载
        print("\n[3/4] 📥 下载文件...")
        urls = [r.get('url', '') for r in classified]
        paths = self.download_manager.download_batch(urls)
        
        for result, path in zip(classified, paths):
            result['local_path'] = path
        
        # 4. 存储
        print("\n[4/4] 💾 存储到数据库...")
        for result in classified:
            if result.get('local_path'):
                resource = {
                    'title': result.get('title'),
                    'url': result.get('url'),
                    'source': result.get('source'),
                    'category': result.get('classification', {}).get('primary_category'),
                    'tags': result.get('classification', {}).get('tags', []),
                    'fingerprint': result.get('classification', {}).get('fingerprint'),
                    'file_path': result.get('local_path'),
                }
                self.db_manager.save_resource(resource)
        
        print("\n" + "=" * 60)
        print(f"✅ 收集完成! 共处理 {len(classified)} 条资料")
        
        return classified
    
    def monitor(self, interval: int = None):
        """启动更新监控"""
        print("\n🔔 启动更新监控...")
        print("-" * 50)
        
        # 添加默认数据源
        self._add_default_sources()
        
        # 检查更新
        updates = self.updater.check_all_sources()
        
        if updates:
            print(f"\n发现 {len(updates)} 个更新:")
            for update in updates:
                print(f"   🔴 {update.source_name}: {update.change_type}")
        else:
            print("\n暂无更新")
        
        # 发送通知
        if updates:
            self.updater.notify_updates(updates)
        
        return updates
    
    def _add_default_sources(self):
        """添加默认数据源"""
        default_sources = [
            {
                'name': '国家标准全文公开系统',
                'url': 'https://open.samr.gov.cn/',
                'enabled': True,
            },
            {
                'name': '国家法律法规数据库',
                'url': 'https://flk.npc.gov.cn/',
                'enabled': True,
            },
            {
                'name': '国务院政策文件库',
                'url': 'https://www.gov.cn/zhengce/content.htm',
                'enabled': True,
            },
        ]
        
        for source in default_sources:
            if source['name'] not in self.updater.sources:
                self.updater.add_source(**source)
    
    def serve(self, host: str = None, port: int = None):
        """启动 API 服务"""
        print("\n🌐 启动 API 服务...")
        print("-" * 50)
        
        api = APIServer(self.config.get_all())
        api.run(
            host=host or self.config.get('API.host', '0.0.0.0'),
            port=port or self.config.get('API.port', 8080)
        )
    
    def stats(self):
        """查看统计信息"""
        print("\n📊 DataCollector 统计信息")
        print("=" * 50)
        
        db_stats = self.db_manager.get_statistics()
        file_stats = self.file_manager.get_statistics()
        download_stats = self.download_manager.get_statistics()
        
        print("\n📚 数据库:")
        print(f"   资源总数: {db_stats.get('total_resources', 0)}")
        print(f"   本周新增: {db_stats.get('this_week', 0)}")
        
        print("\n📁 文件存储:")
        print(f"   文件总数: {file_stats.get('total_files', 0)}")
        print(f"   占用空间: {file_stats.get('total_size_mb', 0)} MB")
        
        print("\n📥 下载统计:")
        print(f"   总任务数: {download_stats.get('total', 0)}")
        print(f"   已完成: {download_stats.get('completed', 0)}")
        print(f"   失败: {download_stats.get('failed', 0)}")
        
        print("\n🏷️ 分类统计:")
        for cat, count in db_stats.get('by_category', {}).items():
            print(f"   {cat}: {count}")
        
        print("\n🔍 来源统计:")
        for source, count in db_stats.get('by_source', {}).items():
            print(f"   {source}: {count}")
        
        print()
    
    def init(self):
        """初始化项目"""
        print("\n🔧 初始化 DataCollector...")
        print("-" * 50)
        
        # 创建目录
        dirs = [
            './data',
            './downloads',
            './logs',
        ]
        
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
            print(f"   ✓ 创建目录: {d}")
        
        print("\n✅ 初始化完成!")
        print("\n下一步:")
        print("   1. 编辑 config/default_config.yaml 配置参数")
        print("   2. 运行 'python main.py stats' 查看状态")
        print("   3. 运行 'python main.py search <关键词>' 开始搜索")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description='DataCollector - 自动化资料收集与管理系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '-c', '--config',
        help='配置文件路径',
        default=None
    )
    
    parser.add_argument(
        '--log-level',
        help='日志级别',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # search 命令
    search_parser = subparsers.add_parser('search', help='搜索资料')
    search_parser.add_argument('query', help='搜索关键词')
    search_parser.add_argument('-e', '--engines', nargs='+', help='使用的搜索引擎')
    search_parser.add_argument('-n', '--max-results', type=int, default=20, help='最大结果数')
    
    # download 命令
    download_parser = subparsers.add_parser('download', help='下载资源')
    download_parser.add_argument('urls', nargs='+', help='文件 URL 列表')
    download_parser.add_argument('-n', '--names', nargs='*', help='自定义文件名')
    
    # collect 命令
    collect_parser = subparsers.add_parser('collect', help='一站式收集')
    collect_parser.add_argument('query', help='搜索关键词')
    collect_parser.add_argument('-n', '--max-results', type=int, default=10, help='最大结果数')
    collect_parser.add_argument('--no-classify', action='store_true', help='跳过分类')
    
    # monitor 命令
    monitor_parser = subparsers.add_parser('monitor', help='启动更新监控')
    monitor_parser.add_argument('-i', '--interval', type=int, help='检查间隔（秒）')
    
    # serve 命令
    serve_parser = subparsers.add_parser('serve', help='启动 API 服务')
    serve_parser.add_argument('-h', '--host', help='监听地址')
    serve_parser.add_argument('-p', '--port', type=int, help='监听端口')
    
    # stats 命令
    subparsers.add_parser('stats', help='查看统计信息')
    
    # init 命令
    subparsers.add_parser('init', help='初始化项目')
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(level=args.log_level)
    logger = logging.getLogger(__name__)
    
    # 执行命令
    if args.command == 'init':
        cli = DataCollectorCLI(args.config)
        cli.init()
        return
    
    if args.command is None:
        parser.print_help()
        return
    
    try:
        cli = DataCollectorCLI(args.config)
        
        if args.command == 'search':
            cli.search(args.query, args.engines, args.max_results)
        
        elif args.command == 'download':
            cli.download(args.urls, args.names)
        
        elif args.command == 'collect':
            cli.collect(args.query, args.max_results, not args.no_classify)
        
        elif args.command == 'monitor':
            cli.monitor(args.interval)
        
        elif args.command == 'serve':
            cli.serve(args.host, args.port)
        
        elif args.command == 'stats':
            cli.stats()
    
    except KeyboardInterrupt:
        print("\n\n👋 已退出")
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
