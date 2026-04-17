"""
任务调度器
支持三种运行模式：
- 定时模式（scheduled）：每日固定时间运行 crawler_engine
- 手动模式（manual）：API触发，适合按需执行
- 自动模式（auto）：结合定时+守护，探索Agent持续运行

配置在 config/global.yaml 的 scheduler 节
"""

import os
import sys
import json
import time
import logging
import signal
import argparse
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from glob import glob

import yaml
import requests

# Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

logger = logging.getLogger('scheduler')


# ═══════════════════════════════════════════════════════════════════
# 全局调度状态
# ═══════════════════════════════════════════════════════════════════

STATE_FILE = os.path.join(BASE_DIR, 'data', 'scheduler_state.json')


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'last_run': None,
        'last_discovery': None,
        'last_level_runs': {},
        'run_count': 0,
    }


def save_state(state: Dict[str, Any]):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════
# 调度器主体
# ═══════════════════════════════════════════════════════════════════

class JobScheduler:
    """
    任务调度器

    三种模式：
    - auto: 每日定时爬取 + 守护探索Agent
    - manual: 仅响应 API 触发
    - scheduled: 仅每日定时爬取（无守护）

    用法：
        scheduler = JobScheduler()
        scheduler.run()          # 阻塞运行
        scheduler.trigger_run()  # 手动触发（API调用）
    """

    def __init__(self, config_path: str = None):
        self.base_dir = BASE_DIR

        # 加载配置
        if config_path is None:
            config_path = os.path.join(self.base_dir, 'config', 'global.yaml')

        self.config = self._load_config(config_path)
        self.scheduler_cfg = self.config.get('scheduler', {})
        self.mode = self.scheduler_cfg.get('mode', 'auto')
        self.daily_run_time = self.scheduler_cfg.get('daily_run_time', '08:30')
        self.timezone = self.scheduler_cfg.get('timezone', 'Asia/Shanghai')
        self.discovery_interval = self.scheduler_cfg.get('discovery_interval_hours', 6)

        # 状态
        self.state = load_state()
        self._stop_event = threading.Event()
        self._daemon_thread: Optional[threading.Thread] = None

        # 引用
        self._crawler_engine = None
        self._discovery_agent = None

        # 设置信号处理
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载全局配置"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}

    # ─── 核心引用 ─────────────────────────────────────────

    @property
    def crawler_engine(self):
        if self._crawler_engine is None:
            from engine.crawler_engine import ConfigDrivenCrawlerEngine
            registry_path = os.path.join(self.base_dir, 'config', 'registry.yaml')
            self._crawler_engine = ConfigDrivenCrawlerEngine(registry_path)
        return self._crawler_engine

    @property
    def discovery_agent(self):
        if self._discovery_agent is None:
            from engine.discovery_agent import DiscoveryAgent
            self._discovery_agent = DiscoveryAgent(self.scheduler_cfg)
        return self._discovery_agent

    # ─── 时间判断 ─────────────────────────────────────────

    def _parse_daily_time(self) -> tuple:
        """解析每日运行时间"""
        h, m = map(int, self.daily_run_time.split(':'))
        return h, m

    def _is_daily_run_due(self) -> bool:
        """判断每日定时是否到点"""
        now = datetime.now()
        target_h, target_m = self._parse_daily_time()

        # 检查今天是否已跑过
        last = self.state.get('last_run', '')
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt.date() == now.date():
                    return False  # 今天已跑
            except Exception:
                pass

        # 检查时间是否已到
        if now.hour == target_h and now.minute >= target_m:
            return True
        if now.hour > target_h:
            return True

        return False

    def _seconds_until_daily_run(self) -> float:
        """计算距离下次定时运行的秒数"""
        now = datetime.now()
        target_h, target_m = self._parse_daily_time()

        next_run = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        return (next_run - now).total_seconds()

    # ─── 执行爬取 ─────────────────────────────────────────

    def run_crawler(self, levels: List[str] = None) -> Dict[str, Any]:
        """
        执行爬虫引擎

        Args:
            levels: 指定层级列表，None=全部

        Returns:
            爬取结果摘要
        """
        lookback = self.config.get('lookback_days', 730)

        logger.info("=" * 60)
        logger.info(f"[Scheduler] 开始爬取 层级={levels} 回查={lookback}天")
        logger.info("=" * 60)

        start = datetime.now()
        result = self.crawler_engine.run_all(
            lookback_days=lookback,
            level_codes=levels,
            concurrent=5,
        )
        elapsed = (datetime.now() - start).total_seconds()

        # 更新状态
        self.state['last_run'] = datetime.now().isoformat()
        self.state['run_count'] = self.state.get('run_count', 0) + 1
        save_state(self.state)

        # 输出摘要
        logger.info(f"\n[Scheduler] 爬取完成，耗时 {elapsed:.1f}s")
        logger.info(f"  总记录: {result['total']}")
        for lv, cnt in sorted(result.get('by_level', {}).items()):
            logger.info(f"  {lv}: {cnt}")

        if result.get('errors'):
            logger.warning(f"  错误: {result['errors']}")

        return result

    # ─── 触发入口 ─────────────────────────────────────────

    def trigger_run(self, levels: List[str] = None) -> Dict[str, Any]:
        """
        手动触发一次爬取（供 API 或外部调用）
        """
        logger.info("[Scheduler] 收到手动触发信号")
        return self.run_crawler(levels=levels)

    def trigger_discovery(self) -> Dict[str, Any]:
        """
        手动触发一次探索
        """
        logger.info("[Scheduler] 收到探索触发信号")
        start = datetime.now()
        leads = self.discovery_agent.run_once()
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(f"[Scheduler] 探索完成，耗时 {elapsed:.1f}s，新增 {len(leads)} 条线索")
        self.state['last_discovery'] = datetime.now().isoformat()
        save_state(self.state)
        return {'leads_found': len(leads), 'elapsed_seconds': elapsed}

    # ─── 定时循环 ─────────────────────────────────────────

    def _scheduled_loop(self):
        """
        定时模式主循环
        每分钟检查一次是否到点
        """
        logger.info(f"[Scheduler] 定时模式启动，每日 {self.daily_run_time} 运行")
        check_interval = 60  # 每分钟检查

        while not self._stop_event.is_set():
            if self._is_daily_run_due():
                logger.info("[Scheduler] 到达定时时间，开始爬取")
                try:
                    self.run_crawler()
                except Exception as e:
                    logger.error(f"[Scheduler] 定时爬取失败: {e}")

            self._stop_event.wait(timeout=check_interval)

        logger.info("[Scheduler] 定时模式已停止")

    # ─── 自动模式（定时 + 守护）──────────────────────────────

    def run_auto(self):
        """
        自动模式：定时爬取 + 探索Agent守护
        """
        logger.info(f"[Scheduler] 自动模式启动")
        logger.info(f"  每日定时爬取: {self.daily_run_time}")
        logger.info(f"  探索间隔: {self.discovery_interval}h")

        # 启动探索Agent守护线程
        self.discovery_agent.start_daemon(interval_hours=self.discovery_interval)

        # 定时循环
        self._scheduled_loop()

        # 停止探索Agent
        self.discovery_agent.stop_daemon()

    # ─── 主入口 ───────────────────────────────────────────

    def run(self):
        """
        根据配置的模式运行调度器
        """
        logger.info(f"[Scheduler] 启动，模式={self.mode}")

        if self.mode == 'auto':
            self.run_auto()
        elif self.mode == 'scheduled':
            self._scheduled_loop()
        elif self.mode == 'manual':
            logger.info("[Scheduler] 手动模式，等待 API 触发（可通过 trigger_run 调用）")
            # 手动模式不阻塞，但保持进程存活
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=60)
        else:
            logger.error(f"[Scheduler] 未知模式: {self.mode}")

        logger.info("[Scheduler] 已退出")

    # ─── 信号处理 ─────────────────────────────────────────

    def _on_signal(self, signum, frame):
        logger.info(f"[Scheduler] 收到信号 {signum}，准备停止")
        self._stop_event.set()

    def stop(self):
        self._stop_event.set()


# ═══════════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════════

def run_scheduler(mode: str = None):
    """便捷入口"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, 'config', 'global.yaml')

    # 临时覆盖模式
    cfg = {}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)

    if mode:
        if 'scheduler' not in cfg:
            cfg['scheduler'] = {}
        cfg['scheduler']['mode'] = mode

    scheduler = JobScheduler(config_path)
    scheduler.run()


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='法规监控任务调度器')
    parser.add_argument('mode', nargs='?', choices=['auto', 'scheduled', 'manual'],
                       help='运行模式（默认从 config/global.yaml 读取）')
    parser.add_argument('--once', action='store_true',
                       help='仅执行一次爬取（不守护）')
    parser.add_argument('--discover', action='store_true',
                       help='仅执行一次探索')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, 'config', 'global.yaml')

    scheduler = JobScheduler(config_path)

    if args.once:
        # 立即执行一次爬取
        result = scheduler.trigger_run()
        print(json.dumps({
            'status': 'ok',
            'total': result.get('total', 0),
            'by_level': result.get('by_level', {}),
        }, ensure_ascii=False, indent=2))

    elif args.discover:
        # 立即执行一次探索
        result = scheduler.trigger_discovery()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        # 正常调度循环
        mode = args.mode
        if mode:
            scheduler.mode = mode
        scheduler.run()
