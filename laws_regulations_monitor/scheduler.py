#!/usr/bin/env python3
"""
[废弃] 此文件已由 scheduler/job_scheduler.py + engine/crawler_engine.py 替代
请使用: python -m scheduler.job_scheduler 或 python -m engine.crawler_engine
"""
定时任务设置脚本
设置每周自动运行的 cron job
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laws_regulations_monitor.monitor import LawsMonitor
import yaml


def setup_cron():
    """设置定时任务"""
    import subprocess
    
    # 获取当前脚本路径
    cli_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'cli.py'
    )
    
    # cron 表达式：每周一早上 9 点
    cron_expr = "0 9 * * 1"
    
    # 构建 cron job 命令
    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = f"cd {work_dir} && python3 {cli_path} --quick >> logs/cron.log 2>&1"
    
    # 检查是否已有相同的 cron job
    existing = subprocess.run(
        ['crontab', '-l'],
        capture_output=True, text=True
    )
    
    job_line = f"{cron_expr} {command}"
    
    if 'laws_regulations_monitor' in existing.stdout:
        print("⚠️ 定时任务已存在，跳过")
        return
    
    # 添加新的 cron job
    new_crontab = existing.stdout + job_line + "\n"
    
    result = subprocess.run(
        ['crontab', '-'],
        input=new_crontab,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ 定时任务已设置: {cron_expr}")
        print(f"   命令: {command}")
    else:
        print(f"❌ 设置失败: {result.stderr}")


def list_cron():
    """列出当前的定时任务"""
    import subprocess
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    if result.returncode == 0:
        print("📋 当前定时任务:")
        print(result.stdout)
    else:
        print("❌ 无法读取定时任务")


def remove_cron():
    """移除定时任务"""
    import subprocess
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    
    if 'laws_regulations_monitor' not in result.stdout:
        print("⚠️ 未找到相关定时任务")
        return
    
    lines = [l for l in result.stdout.split('\n') if 'laws_regulations_monitor' not in l]
    new_crontab = '\n'.join(lines)
    
    result = subprocess.run(['crontab', '-'], input=new_crontab, text=True)
    if result.returncode == 0:
        print("✅ 定时任务已移除")
    else:
        print(f"❌ 移除失败: {result.stderr}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='定时任务管理')
    parser.add_argument('action', choices=['setup', 'list', 'remove'], 
                       help='操作: setup(设置) / list(查看) / remove(移除)')
    
    args = parser.parse_args()
    
    if args.action == 'setup':
        setup_cron()
    elif args.action == 'list':
        list_cron()
    elif args.action == 'remove':
        remove_cron()
