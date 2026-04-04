"""
更新监控器
监控数据源变化，自动提醒更新
"""

import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import requests
from bs4 import BeautifulSoup

from .notifier import Notifier

logger = logging.getLogger(__name__)


@dataclass
class DataSource:
    """数据源"""
    name: str
    url: str
    check_pattern: str = ''
    enabled: bool = True
    last_check: Optional[datetime] = None
    last_hash: Optional[str] = None
    check_interval: int = 24  # 小时
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateInfo:
    """更新信息"""
    source_name: str
    url: str
    detected_at: datetime
    change_type: str  # 'new', 'updated', 'removed'
    details: str = ''
    priority: str = 'normal'  # 'high', 'normal', 'low'


class UpdateMonitor:
    """
    更新监控器
    定期检查数据源变化，发送通知
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化更新监控器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.enabled = config.get('enabled', True)
        self.check_interval = config.get('check_interval', 24)
        
        # 初始化数据源
        self.sources: Dict[str, DataSource] = {}
        self._init_sources()
        
        # 初始化通知器
        self.notifier = Notifier(config.get('notify', []))
        
        # 更新历史
        self.update_history: List[UpdateInfo] = []
        
        # 回调函数
        self.on_update_callbacks: List[Callable] = []
    
    def _init_sources(self) -> None:
        """初始化数据源"""
        sources_config = self.config.get('sources', [])
        
        for src_config in sources_config:
            source = DataSource(
                name=src_config.get('name', ''),
                url=src_config.get('url', ''),
                check_pattern=src_config.get('check_pattern', ''),
                enabled=src_config.get('enabled', True),
            )
            self.sources[source.name] = source
        
        logger.info(f"已加载 {len(self.sources)} 个监控数据源")
    
    def add_source(self, name: str, url: str, check_pattern: str = '', **kwargs) -> None:
        """
        添加监控数据源
        
        Args:
            name: 数据源名称
            url: 数据源URL
            check_pattern: 检查模式（CSS选择器或XPath）
            **kwargs: 其他参数
        """
        source = DataSource(
            name=name,
            url=url,
            check_pattern=check_pattern,
            **kwargs
        )
        self.sources[name] = source
        logger.info(f"添加监控数据源: {name}")
    
    def remove_source(self, name: str) -> bool:
        """
        移除数据源
        
        Args:
            name: 数据源名称
            
        Returns:
            是否成功移除
        """
        if name in self.sources:
            del self.sources[name]
            logger.info(f"移除监控数据源: {name}")
            return True
        return False
    
    def check_source(self, name: str) -> Optional[UpdateInfo]:
        """
        检查单个数据源的更新
        
        Args:
            name: 数据源名称
            
        Returns:
            更新信息，无更新返回 None
        """
        if name not in self.sources:
            logger.warning(f"数据源不存在: {name}")
            return None
        
        source = self.sources[name]
        
        if not source.enabled:
            return None
        
        try:
            current_hash = self._fetch_content_hash(source)
            
            if current_hash is None:
                return None
            
            # 首次检查，无历史记录
            if source.last_hash is None:
                source.last_hash = current_hash
                source.last_check = datetime.now()
                return None
            
            # 比较哈希值
            if current_hash != source.last_hash:
                update_info = UpdateInfo(
                    source_name=name,
                    url=source.url,
                    detected_at=datetime.now(),
                    change_type='updated' if source.last_hash else 'new',
                    details=f"内容哈希从 {source.last_hash[:8]}... 变为 {current_hash[:8]}...",
                    priority=self._determine_priority(source),
                )
                
                # 更新状态
                source.last_hash = current_hash
                source.last_check = datetime.now()
                
                # 记录历史
                self.update_history.append(update_info)
                
                return update_info
            
            source.last_check = datetime.now()
            return None
        
        except Exception as e:
            logger.error(f"检查数据源 {name} 失败: {e}")
            return None
    
    def check_all_sources(self) -> List[UpdateInfo]:
        """
        检查所有数据源
        
        Returns:
            更新信息列表
        """
        updates = []
        
        for name in self.sources:
            update = self.check_source(name)
            if update:
                updates.append(update)
                
                # 触发回调
                for callback in self.on_update_callbacks:
                    try:
                        callback(update)
                    except Exception as e:
                        logger.error(f"回调执行失败: {e}")
        
        return updates
    
    def _fetch_content_hash(self, source: DataSource) -> Optional[str]:
        """获取内容哈希"""
        try:
            response = requests.get(
                source.url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                timeout=30
            )
            response.raise_for_status()
            
            content = response.text
            
            # 如果有检查模式，提取相关内容
            if source.check_pattern:
                soup = BeautifulSoup(content, 'html.parser')
                elements = soup.select(source.check_pattern)
                content = '\n'.join(str(el) for el in elements)
            
            # 计算哈希
            return hashlib.md5(content.encode('utf-8')).hexdigest()
        
        except Exception as e:
            logger.error(f"获取内容失败 {source.name}: {e}")
            return None
    
    def _determine_priority(self, source: DataSource) -> str:
        """确定优先级"""
        # 根据数据源类型确定优先级
        high_priority_keywords = ['法律', '法规', '政策', '重要', '紧急']
        
        for keyword in high_priority_keywords:
            if keyword in source.name:
                return 'high'
        
        return 'normal'
    
    def notify_updates(self, updates: List[UpdateInfo]) -> None:
        """
        发送更新通知
        
        Args:
            updates: 更新信息列表
        """
        if not updates:
            return
        
        self.notifier.send(updates)
    
    def register_callback(self, callback: Callable) -> None:
        """
        注册更新回调
        
        Args:
            callback: 回调函数，接收 UpdateInfo 参数
        """
        self.on_update_callbacks.append(callback)
    
    def get_update_history(
        self,
        source_name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取更新历史
        
        Args:
            source_name: 数据源名称过滤
            since: 时间过滤
            limit: 返回数量限制
            
        Returns:
            更新历史列表
        """
        history = self.update_history
        
        if source_name:
            history = [h for h in history if h.source_name == source_name]
        
        if since:
            history = [h for h in history if h.detected_at >= since]
        
        # 转换为字典
        return [
            {
                'source_name': h.source_name,
                'url': h.url,
                'detected_at': h.detected_at.isoformat(),
                'change_type': h.change_type,
                'details': h.details,
                'priority': h.priority,
            }
            for h in history[-limit:]
        ]
    
    def get_source_status(self) -> List[Dict[str, Any]]:
        """获取所有数据源状态"""
        return [
            {
                'name': source.name,
                'url': source.url,
                'enabled': source.enabled,
                'last_check': source.last_check.isoformat() if source.last_check else None,
                'check_interval': source.check_interval,
            }
            for source in self.sources.values()
        ]
    
    def start_monitoring(self, interval: Optional[int] = None) -> None:
        """
        开始监控循环
        
        Args:
            interval: 检查间隔（秒），默认使用配置值
        """
        interval = interval or self.check_interval * 3600
        
        logger.info(f"开始监控，间隔 {interval} 秒")
        
        while True:
            try:
                updates = self.check_all_sources()
                if updates:
                    self.notify_updates(updates)
                    logger.info(f"检测到 {len(updates)} 个更新")
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
            
            time.sleep(interval)
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        self.enabled = False
        logger.info("停止监控")
