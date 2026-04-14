"""
法律合规监控 - 定时任务触发脚本
通过 OpenClaw cron job 调用，生成监控指令
"""

import os
import sys
import json
from datetime import datetime

LOG_DIR = os.path.expanduser('~/workspace/agent/workspace/data-collector/logs')
os.makedirs(LOG_DIR, exist_ok=True)

TASK_FILE = os.path.join(LOG_DIR, 'pending_monitor_task.json')


def create_task(levels=None, priority='normal'):
    """创建待执行的监控任务"""
    task = {
        'created_at': datetime.now().isoformat(),
        'levels': levels or ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case'],
        'priority': priority,
        'status': 'pending',
        'lookback_days': 30,
    }

    with open(TASK_FILE, 'w', encoding='utf-8') as f:
        json.dump(task, f, ensure_ascii=False, indent=2)

    print(f"✅ 监控任务已创建: {TASK_FILE}")
    print(f"   层级: {task['levels']}")
    print(f"   优先级: {priority}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='创建法律监控任务')
    parser.add_argument('--levels', '-l', nargs='+',
                        choices=['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case'],
                        help='指定检查的层级')
    parser.add_argument('--urgent', '-u', action='store_true',
                        help='高优先级（立即通知）')

    args = parser.parse_args()

    priority = 'high' if args.urgent else 'normal'
    create_task(levels=args.levels, priority=priority)
