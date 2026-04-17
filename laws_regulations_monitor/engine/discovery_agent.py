"""
探索Agent
定期搜索立法动态、行业新闻，发现新线索

核心职责：
- 维护已搜索关键词集合（避免重复）
- 定期搜索立法动态、行业新闻
- 探索微信公众号、行业论坛等非官方渠道
- 结果写入 data/discovered_leads.json
- 发现新线索后判断是否触发 crawler_engine 补爬
"""

import os
import sys
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from threading import Thread, Event
import threading

# Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

logger = logging.getLogger('engine.discovery')


# ═══════════════════════════════════════════════════════════════════
# 搜索关键词池
# ═══════════════════════════════════════════════════════════════════

# 立法动态关键词
LEGISLATION_KEYWORDS = [
    '数据安全法 征求意见',
    '个人信息保护法 实施细则',
    '网络安全法 修订',
    '关键信息基础设施保护条例 征求意见',
    '数据出境管理条例',
    '人工智能法 草案',
    '生成式AI 管理规定',
    '个人信息出境标准合同',
    '汽车数据安全管理若干规定',
    '工业和信息化领域数据安全管理办法',
    '金融数据安全分级指南',
    '电信数据安全管理办法',
    '网络数据安全管理条例',
    '数据交易服务安全要求',
]

# 行业新闻关键词
INDUSTRY_KEYWORDS = [
    '数据安全 监管 处罚',
    '个人信息保护 典型案例',
    'App违法违规收集使用个人信息',
    '网络安全审查 滴滴',
    '数据跨境 安全评估',
    '等保测评 通过',
    '数据分类分级 落地',
    '个人信息保护认证',
    '数据出境企业 名单',
    '网络数据安全应急演练',
]


# ═══════════════════════════════════════════════════════════════════
# 发现线索的数据结构
# ═══════════════════════════════════════════════════════════════════

class LeadsStore:
    """
    线索持久化存储
    维护 discovered_leads.json
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.leads: List[Dict[str, Any]] = []
        self._seen_urls: Set[str] = set()
        self._seen_titles: Set[str] = set()
        self._load()

    def _load(self):
        """加载已有线索"""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.leads = data if isinstance(data, list) else data.get('leads', [])
                for lead in self.leads:
                    if lead.get('url'):
                        self._seen_urls.add(lead['url'])
                    if lead.get('title'):
                        self._seen_titles.add(lead['title'])
                logger.info(f"  已加载 {len(self.leads)} 条历史线索")
            except Exception as e:
                logger.warning(f"  线索文件读取失败: {e}")
                self.leads = []

    def save(self):
        """保存线索到文件"""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'updated_at': datetime.now().isoformat(),
                        'total': len(self.leads),
                        'leads': self.leads,
                    }, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"  保存线索失败: {e}")

    def add_lead(self, lead: Dict[str, Any]) -> bool:
        """
        添加新线索
        Returns: True if new (added), False if duplicate
        """
        url = lead.get('url', '')
        title = lead.get('title', '')

        # 基于 URL 或 title 去重
        if url and url in self._seen_urls:
            return False
        if title and title in self._seen_titles:
            return False

        with self._lock:
            lead['discovered_at'] = datetime.now().isoformat()
            lead['discovered_by'] = 'discovery_agent'
            self.leads.append(lead)
            if url:
                self._seen_urls.add(url)
            if title:
                self._seen_titles.add(title)
        return True

    def add_leads(self, leads: List[Dict[str, Any]]) -> int:
        """批量添加线索，返回新增数量"""
        count = 0
        for lead in leads:
            if self.add_lead(lead):
                count += 1
        if count > 0:
            self.save()
        return count

    def get_recent(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近 N 天的新线索"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for lead in self.leads:
            disc = lead.get('discovered_at', '')
            if disc:
                try:
                    dt = datetime.fromisoformat(disc.replace('Z', '+00:00'))
                    if dt >= cutoff:
                        recent.append(lead)
                except Exception:
                    pass
        return recent

    def get_uncrawled(self) -> List[Dict[str, Any]]:
        """获取尚未触发爬取的线索"""
        return [
            lead for lead in self.leads
            if not lead.get('crawled', False)
        ]


# ═══════════════════════════════════════════════════════════════════
# Web 搜索器（模拟真实搜索，暂用 DuckDuckGo 风格）
# ═══════════════════════════════════════════════════════════════════

class WebSearcher:
    """
    Web 搜索
    注意：这里需要实际的搜索 API key 或爬虫实现
    当前为框架实现，具体搜索能力待接入
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.session = requests.Session() if 'requests' in dir() else None

    def search(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """
        执行搜索
        当前框架预留，未来可接入：
        - DuckDuckGo API
        - 百度搜索 API
        - 微信公众号搜索
        - 行业论坛爬虫
        """
        # 占位：实际搜索能力待接入
        # 这里可以返回空列表，由实际搜索实现填充
        logger.info(f"  [Searcher] query={query[:30]} (待接入真实搜索API)")
        return []


# ═══════════════════════════════════════════════════════════════════
# 探索Agent
# ═══════════════════════════════════════════════════════════════════

class DiscoveryAgent:
    """
    探索Agent

    职责：
    - 定期搜索立法动态和行业新闻
    - 探索微信公众号、行业论坛等非官方渠道
    - 结果写入 data/discovered_leads.json
    - 判断是否需要触发 crawler_engine 补爬
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_dir = BASE_DIR

        # 线索存储
        leads_path = os.path.join(self.base_dir, 'data', 'discovered_leads.json')
        self.store = LeadsStore(leads_path)

        # 已搜索关键词集合
        self._searched_keywords: Set[str] = set()

        # 搜索关键词列表
        self.legislation_kw = self.config.get('legislation_keywords', LEGISLATION_KEYWORDS)
        self.industry_kw = self.config.get('industry_keywords', INDUSTRY_KEYWORDS)

        # Web 搜索器
        self.searcher = WebSearcher(self.config)

        # 停止事件
        self._stop_event = Event()
        self._daemon_thread: Optional[Thread] = None

        # 爬虫引擎引用（延迟导入避免循环）
        self._crawler_engine = None

        # 触发爬取的阈值
        self.trigger_threshold = self.config.get('trigger_threshold', 3)

    @property
    def crawler_engine(self):
        """延迟加载爬虫引擎"""
        if self._crawler_engine is None:
            from engine.crawler_engine import ConfigDrivenCrawlerEngine
            registry_path = os.path.join(self.base_dir, 'config', 'registry.yaml')
            self._crawler_engine = ConfigDrivenCrawlerEngine(registry_path)
        return self._crawler_engine

    # ─── 搜索新线索 ─────────────────────────────────────────

    def search_new_leads(self) -> List[Dict[str, Any]]:
        """
        执行一次探索搜索

        Returns:
            新发现的线索列表
        """
        all_kw = self.legislation_kw + self.industry_kw
        new_kw = [kw for kw in all_kw if kw not in self._searched_keywords]

        logger.info(f"\n══ DiscoveryAgent: 搜索 {len(new_kw)} 个新关键词 ══")

        new_leads = []
        for kw in new_kw:
            try:
                leads = self._search_keyword(kw)
                new_leads.extend(leads)
                self._searched_keywords.add(kw)
                logger.info(f"  [{kw[:20]}]: {len(leads)} 条线索")
                time.sleep(1)  # 避免请求过快
            except Exception as e:
                logger.error(f"  [{kw[:20]}] 搜索失败: {e}")

        # 去重后添加
        added = self.store.add_leads(new_leads)
        logger.info(f"  新增 {added} 条线索（去重后）")

        return new_leads

    def _search_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索单个关键词
        当前为框架预留，实际搜索能力待接入
        """
        # 框架预留：这里应接入真实搜索
        # 如 DuckDuckGo、百度、搜狗搜索等
        results = self.searcher.search(keyword, count=10)

        leads = []
        for r in results:
            leads.append({
                'keyword': keyword,
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'snippet': r.get('snippet', ''),
                'source': r.get('source', 'search'),
                'date': r.get('date', ''),
                'type': self._classify_lead(r.get('title', ''), r.get('snippet', '')),
                'crawled': False,
            })
        return leads

    def _classify_lead(self, title: str, snippet: str) -> str:
        """判断线索类型"""
        text = (title + snippet).lower()

        if any(k in text for k in ['征求意见', '草案', '起草', '立项']):
            return 'legislation_draft'
        elif any(k in text for k in ['征求意见', '反馈', '意见']):
            return 'legislation_review'
        elif any(k in text for k in ['处罚', '罚款', '通报', '违法']):
            return 'enforcement'
        elif any(k in text for k in ['发布', '施行', '实施', '生效']):
            return 'legislation_publish'
        elif any(k in text for k in ['标准', '规范', '指南', 'GB', 'JR/T', 'YD/T']):
            return 'standard'
        else:
            return 'industry_news'

    # ─── 判断是否触发爬取 ───────────────────────────────────

    def should_crawl(self, lead: Dict[str, Any]) -> bool:
        """
        判断发现的新线索是否值得触发爬虫引擎补爬

        判断依据：
        - 涉及法规层级（L1-L4）优先级高
        - 是新发布/征求意见中的法规
        - 来源权威（政府网站、官方公众号）
        """
        lead_type = lead.get('type', '')
        title = lead.get('title', '')
        url = lead.get('url', '')
        source = lead.get('source', '')

        # 高优先级线索类型
        high_priority_types = {
            'legislation_draft',   # 征求意见稿
            'legislation_publish', # 新发布法规
            'legislation_review',  # 意见征集
        }

        if lead_type not in high_priority_types:
            return False

        # 权威来源优先
        authoritative_domains = [
            'gov.cn', 'cac.gov.cn', 'miit.gov.cn', 'mps.gov.cn',
            'pbc.gov.cn', 'samr.gov.cn', 'npc.gov.cn', 'court.gov.cn',
            'moe.gov.cn', 'mot.gov.cn', 'nhc.gov.cn',
        ]
        is_authoritative = any(d in url for d in authoritative_domains)

        # 有高置信度关键词的也触发
        high_signal_keywords = [
            '数据安全', '个人信息', '网络安全', '关键信息基础设施',
            '汽车数据', '生成式AI', '人工智能', '算法', '深度合成',
            '数据出境', '数据跨境', '等级保护', '数据分类分级',
            '工业数据', '金融数据', '儿童个人信息', 'App',
        ]
        has_signal = any(kw in title for kw in high_signal_keywords)

        return is_authoritative or has_signal

    def trigger_crawl(self, lead: Dict[str, Any]):
        """触发爬虫引擎补爬"""
        level_code = self._infer_level(lead)
        if not level_code:
            logger.info(f"  无法推断层级，跳过补爬: {lead.get('title', '')[:30]}")
            return

        logger.info(f"  → 触发补爬: [{level_code}] {lead.get('title', '')[:40]}")
        try:
            results = self.crawler_engine.run_level(level_code)
            lead['crawled'] = True
            lead['crawled_at'] = datetime.now().isoformat()
            lead['crawl_results'] = len(results)
            self.store.save()
        except Exception as e:
            logger.error(f"  补爬失败: {e}")

    def _infer_level(self, lead: Dict[str, Any]) -> Optional[str]:
        """从线索推断法规层级"""
        title = lead.get('title', '') + lead.get('snippet', '')
        url = lead.get('url', '')

        if any(k in title for k in ['法律', '全国人民代表大会', '全国人大常委会']):
            return 'L1'
        if any(k in title for k in ['行政法规', '网络数据安全管理条例',
                                      '关键信息基础设施保护条例', '数据出境']):
            return 'L2'
        if any(k in title for k in ['办法', '规定', '通知', '决定', '意见',
                                      '指南', '规范', '标准', '个人信息']):
            return 'L3'
        if any(k in title for k in ['GB', '国家标准', '推荐性', '强制性']):
            return 'L4'
        if any(k in title for k in ['JR/T', 'YD/T', 'GA/T', '金融行业', '电信']):
            return 'L5'

        # 从 URL 推断
        domain = url.lower()
        if 'cac.gov.cn' in domain:
            return 'L3'
        if 'samr.gov.cn' in domain or 'openstd.samr.gov.cn' in domain:
            return 'L4'
        if 'miit.gov.cn' in domain:
            return 'L3'

        return None

    # ─── 后台守护模式 ────────────────────────────────────────

    def run_once(self):
        """执行一次探索"""
        new_leads = self.search_new_leads()

        if new_leads:
            # 检查是否需要触发爬取
            for lead in new_leads:
                if self.should_crawl(lead):
                    self.trigger_crawl(lead)

        return new_leads

    def run_daemon(self, interval_hours: int = 6):
        """
        后台守护模式
        每隔 interval_hours 小时执行一次探索

        Args:
            interval_hours: 探索间隔（小时）
        """
        interval_seconds = interval_hours * 3600
        logger.info(f"DiscoveryAgent 守护模式启动，间隔 {interval_hours}h")

        self._stop_event.clear()

        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"DiscoveryAgent 执行异常: {e}")

            # 等待下一次执行或停止信号
            self._stop_event.wait(timeout=interval_seconds)

        logger.info("DiscoveryAgent 守护模式已停止")

    def start_daemon(self, interval_hours: int = 6):
        """启动守护线程"""
        if self._daemon_thread and self._daemon_thread.is_alive():
            logger.warning("守护线程已在运行中")
            return

        self._stop_event.clear()
        self._daemon_thread = Thread(
            target=self.run_daemon,
            args=(interval_hours,),
            daemon=True,
            name='DiscoveryAgent-Daemon'
        )
        self._daemon_thread.start()
        logger.info(f"守护线程已启动（间隔 {interval_hours}h）")

    def stop_daemon(self):
        """停止守护线程"""
        self._stop_event.set()
        if self._daemon_thread:
            self._daemon_thread.join(timeout=5)
        logger.info("守护线程已停止")

    # ─── 状态查询 ───────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """返回当前状态"""
        return {
            'searched_keywords_count': len(self._searched_keywords),
            'total_leads': len(self.store.leads),
            'recent_leads_7d': len(self.store.get_recent(7)),
            'uncrawled_leads': len(self.store.get_uncrawled()),
            'daemon_running': self._daemon_thread is not None and self._daemon_thread.is_alive(),
        }
