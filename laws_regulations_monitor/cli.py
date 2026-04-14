"""
法律法规监控命令行工具
用法:
    python cli.py --levels L1 L3 case           # 只检查指定层级
    python cli.py --nodownload                  # 不下载文件
    python cli.py --report                       # 输出详细报告
    python cli.py --init                         # 初始化（首次运行）
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laws_regulations_monitor.monitor import LawsMonitor


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='📋 法律合规数据库自动监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py                           # 完整扫描
  python cli.py --levels L1 L3           # 只检查 L1 和 L3
  python cli.py --nodownload              # 检查但不下文件
  python cli.py --init                    # 首次初始化
  python cli.py --quick                   # 快速检查
  
层级选项:
  L1-国家法律 | L2-行政法规 | L3-部门文件
  L4-国家标准 | L5-行业标准 | L6-地方文件 | L7-地方标准
  case-执法案例库 | all-全部（默认）
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default=None,
        help='配置文件路径（默认: config.yaml）'
    )
    
    parser.add_argument(
        '--levels', '-l',
        nargs='+',
        choices=['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case', 'all'],
        default=['all'],
        help='指定监控层级（默认: all）'
    )
    
    parser.add_argument(
        '--nodownload',
        action='store_true',
        help='仅检查，不下载文件'
    )
    
    parser.add_argument(
        '--report', '-r',
        action='store_true',
        help='输出详细报告'
    )
    
    parser.add_argument(
        '--init',
        action='store_true',
        help='首次初始化（加载现有库记录）'
    )
    
    parser.add_argument(
        '--quick', '-q',
        action='store_true',
        help='快速检查（不下文件，不写飞书）'
    )
    
    args = parser.parse_args()
    
    # 解析层级
    levels = None
    if 'all' not in args.levels:
        levels = args.levels
    
    # 加载配置
    config_path = args.config
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__), 'config.yaml'
        )
    
    try:
        monitor = LawsMonitor(config_path)
    except FileNotFoundError:
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)
    
    # 执行扫描
    if args.init:
        print("🔄 初始化中...")
        monitor._init_crawlers()
        if monitor.comparator:
            monitor.comparator.load_existing()
        stats = monitor.bitable.get_table_stats()
        print("✅ 初始化完成！当前库状态:")
        for name, count in stats.items():
            print(f"  • {name}: {count} 条")
        return
    
    if args.quick:
        print("🔍 执行快速检查...")
        results = monitor.run_full_scan(levels=levels, download=False)
    else:
        print("🔍 开始监控扫描...")
        results = monitor.run_full_scan(levels=levels, download=not args.nodownload)
    
    # 输出报告
    if args.report:
        print("\n" + "=" * 60)
        print("📋 报告")
        print("=" * 60)
        print(results['report'])
    else:
        # 简洁输出
        total_new = sum(
            len(r.get('bitable', {}).get('created', []))
            for r in results.get('results', {}).values()
        )
        total_errors = sum(
            len(r.get('bitable', {}).get('errors', []))
            for r in results.get('results', {}).values()
        )
        
        if total_new > 0:
            print(f"✅ 完成! 新增 {total_new} 条" + 
                  (f", 失败 {total_errors} 条" if total_errors else ""))
        else:
            print("✅ 扫描完成，未发现新增法规")


if __name__ == '__main__':
    main()
