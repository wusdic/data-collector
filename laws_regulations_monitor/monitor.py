"""
法律法规监控主程序
调度爬虫 → 比对 → 存储 → 通知
"""

import os
import sys
import logging
import yaml
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LawsMonitor:
    """法律法规监控主程序"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), 'config.yaml'
            )
        
        self.config = self._load_config(config_path)
        self._setup_logging()
        
        # 初始化客户端
        self.bitable = self._init_bitable()
        self.github = self._init_github()
        self.comparator = self._init_comparator()
        
        # 爬虫实例
        self.crawlers = {}

    def _load_config(self, path: str) -> Dict[str, Any]:
        """加载配置文件"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        logger.info(f"配置文件加载成功: {path}")
        return config

    def _setup_logging(self) -> None:
        """配置日志"""
        log_dir = './logs'
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(
            log_dir, 
            f"laws_monitor_{datetime.now().strftime('%Y%m%d')}.log"
        )
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def _init_bitable(self):
        """初始化飞书多维表格客户端"""
        try:
            from .bitable_client import BitableClient
            bitable_config = self.config['BITABLE']
            client = BitableClient(bitable_config)
            logger.info("飞书多维表格客户端初始化成功")
            return client
        except Exception as e:
            logger.error(f"飞书客户端初始化失败: {e}")
            return None

    def _init_github(self):
        """初始化 GitHub 客户端"""
        try:
            from .github_client import GitHubClient
            github_config = self.config['GITHUB']
            client = GitHubClient(github_config)
            logger.info("GitHub 客户端初始化成功")
            return client
        except Exception as e:
            logger.error(f"GitHub 客户端初始化失败: {e}")
            return None

    def _init_comparator(self):
        """初始化比对引擎"""
        if self.bitable:
            from .comparator import Comparator
            return Comparator(self.bitable, self.github)
        return None

    def _init_crawlers(self) -> None:
        """初始化所有爬虫"""
        if not self.crawlers:
            self.crawlers = {
                'FLK': self._create_flk_crawler(),
                'SAMR': self._create_samr_crawler(),
                'CAC': self._create_cac_crawler(),
            }
            logger.info(f"已初始化 {len(self.crawlers)} 个爬虫")

    def _create_flk_crawler(self):
        """创建 FLK 爬虫"""
        try:
            from .crawlers.flk_crawler import FLKCrawler
            flk_sources = self.config['LEVELS']['L1_国家法律']['sources']
            for src in flk_sources:
                if 'flk' in src.get('url', '').lower() or 'npc' in src.get('url', '').lower():
                    config = {
                        'base_url': src.get('base_url', src.get('url', '')),
                        'search_url': src.get('search_url', ''),
                        'request_delay': 2.0,
                    }
                    return FLKCrawler(config, self.config['MONITOR']['lookback_days'])
            
            # 默认配置
            return FLKCrawler(
                {'base_url': 'https://flk.npc.gov.cn/', 
                 'search_url': 'https://flk.npc.gov.cn/api/v2/'},
                self.config['MONITOR']['lookback_days']
            )
        except Exception as e:
            logger.error(f"FLK 爬虫创建失败: {e}")
            return None

    def _create_samr_crawler(self):
        """创建 SAMR 爬虫"""
        try:
            from .crawlers.samr_crawler import SAMRCrawler
            samr_sources = self.config['LEVELS']['L4_国家标准']['sources']
            for src in samr_sources:
                if 'samr' in src.get('url', '').lower() or 'openstd' in src.get('url', '').lower():
                    config = {
                        'base_url': src.get('base_url', src.get('url', '')),
                        'search_url': src.get('search_url', ''),
                        'request_delay': 2.0,
                    }
                    return SAMRCrawler(config, self.config['MONITOR']['lookback_days'])
            
            return SAMRCrawler(
                {'base_url': 'https://openstd.samr.gov.cn/',
                 'search_url': 'https://openstd.samr.gov.cn/bzgk/gb/'},
                self.config['MONITOR']['lookback_days']
            )
        except Exception as e:
            logger.error(f"SAMR 爬虫创建失败: {e}")
            return None

    def _create_cac_crawler(self):
        """创建 CAC 爬虫"""
        try:
            from .crawlers.cac_crawler import CACCrawler
            cac_sources = self.config['LEVELS']['L3_部门文件']['sources']
            for src in cac_sources:
                if 'cac' in src.get('url', '').lower():
                    config = {
                        'base_url': src.get('base_url', src.get('url', '')),
                        'search_url': src.get('search_url', ''),
                        'request_delay': 2.0,
                    }
                    return CACCrawler(config, self.config['MONITOR']['lookback_days'])
            
            return CACCrawler(
                {'base_url': 'https://www.cac.gov.cn/',
                 'search_url': 'https://www.cac.gov.cn/search/'},
                self.config['MONITOR']['lookback_days']
            )
        except Exception as e:
            logger.error(f"CAC 爬虫创建失败: {e}")
            return None

    def run_full_scan(self, levels: List[str] = None, 
                       download: bool = True) -> Dict[str, Any]:
        """
        执行完整扫描
        
        Args:
            levels: 指定层级，如 ['L1', 'L3', 'case']，None 表示全部
            download: 是否下载文件
            
        Returns:
            扫描结果报告
        """
        logger.info("=" * 60)
        logger.info("开始法律法规监控扫描")
        logger.info("=" * 60)
        
        if levels is None:
            levels = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case']
        
        # 1. 初始化爬虫
        self._init_crawlers()
        
        # 2. 加载现有记录
        if self.comparator:
            self.comparator.load_existing()
        
        all_results = {}
        all_items = {}  # level -> items
        
        # 3. 调度爬虫
        logger.info("步骤1: 爬取数据源...")
        
        # FLK: L1, L2
        if 'L1' in levels or 'L2' in levels:
            if self.crawlers.get('FLK'):
                flk_results = self.crawlers['FLK'].crawl_all()
                for item in flk_results:
                    level = item.get('level', 'L1')
                    if level not in all_items:
                        all_items[level] = []
                    all_items[level].append(item)
                logger.info(f"FLK 爬取完成: {len(flk_results)} 条")
        
        # SAMR: L4
        if 'L4' in levels:
            if self.crawlers.get('SAMR'):
                samr_results = self.crawlers['SAMR'].crawl_all()
                all_items['L4'] = samr_results
                logger.info(f"SAMR 爬取完成: {len(samr_results)} 条")
        
        # CAC: L3 + 执法案例
        if 'L3' in levels or 'case' in levels:
            if self.crawlers.get('CAC'):
                cac_results = self.crawlers['CAC'].crawl_all()
                all_items['L3'] = []
                all_items['case'] = []
                for item in cac_results:
                    if item.get('level') == 'case':
                        all_items['case'].append(item)
                    else:
                        all_items['L3'].append(item)
                logger.info(f"CAC 爬取完成: {len(cac_results)} 条")
        
        # 4. 比对和保存
        logger.info("步骤2: 比对现有库...")
        if self.comparator:
            for level in levels:
                items = all_items.get(level, [])
                if not items:
                    continue
                
                new_records, updated, skipped = self.comparator.find_new_records(items, level)
                
                logger.info(f"[{level}] 新增: {len(new_records)}, 更新: {len(updated)}, 跳过: {len(skipped)}")
                
                # 5. 保存到飞书 + GitHub
                if new_records:
                    logger.info(f"[{level}] 保存新记录...")
                    result = self.comparator.merge_and_save(new_records, level, download)
                    all_results[level] = result
                else:
                    all_results[level] = {'bitable': {'created': [], 'updated': [], 'errors': []},
                                         'github': {'uploaded': [], 'skipped': [], 'failed': []}}
        else:
            logger.warning("比对引擎未初始化，跳过比对步骤")
        
        # 6. 生成报告
        report = self._generate_report(all_results)
        
        # 7. 发送通知
        if self.config['MONITOR']['notify'].get('enabled'):
            self._send_notification(report)
        
        logger.info("=" * 60)
        logger.info("扫描完成!")
        logger.info("=" * 60)
        
        return {
            'results': all_results,
            'report': report,
            'timestamp': datetime.now().isoformat(),
        }

    def _generate_report(self, results: Dict[str, Any]) -> str:
        """生成报告"""
        lines = [
            "📋 **法律法规监控报告**",
            "",
            f"🕐 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
        
        level_names = {
            'L1': 'L1-国家法律',
            'L2': 'L2-行政法规',
            'L3': 'L3-部门文件',
            'L4': 'L4-国家标准',
            'L5': 'L5-行业标准',
            'L6': 'L6-地方文件',
            'L7': 'L7-地方标准',
            'case': '执法案例库',
        }
        
        total_new = 0
        total_errors = 0
        has_new = False
        
        for level, result in results.items():
            bitable_res = result.get('bitable', {})
            github_res = result.get('github', {})
            
            created = len(bitable_res.get('created', []))
            errors = len(bitable_res.get('errors', []))
            github_ok = len(github_res.get('uploaded', []))
            
            total_new += created
            total_errors += errors
            
            if created > 0:
                has_new = True
                lines.append(f"**{level_names.get(level, level)}**")
                lines.append(f"  • 新增: {created} 条")
                lines.append(f"  • 文件上传: {github_ok} 个")
                if errors > 0:
                    lines.append(f"  • 失败: {errors} 条")
                lines.append("")
                
                # 列出前5条
                for title in bitable_res.get('created', [])[:5]:
                    lines.append(f"  🔹 {title}")
                if len(bitable_res.get('created', [])) > 5:
                    lines.append(f"  ... 还有 {len(bitable_res['created']) - 5} 条")
                lines.append("")
        
        if not has_new:
            lines.append("✅ 本次扫描未发现新增法规")
        else:
            lines.append(f"**汇总**: 新增 {total_new} 条" + 
                        (f"，失败 {total_errors} 条" if total_errors else ""))
        
        lines.append("")
        lines.append("> 🤖 由 LawRegulationsMonitor 自动生成")
        
        return '\n'.join(lines)

    def _send_notification(self, report: str) -> None:
        """发送飞书通知"""
        try:
            from .notifier import LawsNotifier
            notifier = LawsNotifier(self.config['MONITOR']['notify'])
            notifier.send(report)
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    def quick_check(self) -> Dict[str, int]:
        """快速检查（仅比对，不下载）"""
        return self.run_full_scan(download=False)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='法律法规监控工具')
    parser.add_argument('--config', '-c', default=None, help='配置文件路径')
    parser.add_argument('--levels', '-l', nargs='+', 
                       choices=['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case'],
                       help='指定监控层级')
    parser.add_argument('--nodownload', action='store_true', help='不下载文件')
    parser.add_argument('--report', '-r', action='store_true', help='输出报告')
    
    args = parser.parse_args()
    
    monitor = LawsMonitor(args.config)
    results = monitor.run_full_scan(
        levels=args.levels, 
        download=not args.nodownload
    )
    
    if args.report:
        print(results['report'])


if __name__ == '__main__':
    main()
