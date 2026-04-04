"""
统一搜索接口
提供统一的搜索入口，支持多种搜索引擎
"""

import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from .engines.google_engine import GoogleSearchEngine
from .engines.bing_engine import BingSearchEngine
from .engines.baidu_engine import BaiduSearchEngine
from .engines.duckduckgo_engine import DuckDuckGoEngine
from .engines.feishu_engine import FeishuSearchEngine

logger = logging.getLogger(__name__)


class BaseSearchEngine(ABC):
    """搜索引擎基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__.replace('SearchEngine', '').lower()
    
    @abstractmethod
    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            **kwargs: 其他参数
            
        Returns:
            搜索结果列表
        """
        pass
    
    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """标准化搜索结果格式"""
        return {
            'title': result.get('title', ''),
            'url': result.get('url', result.get('link', '')),
            'snippet': result.get('snippet', result.get('description', '')),
            'source': self.name,
        }


class SearchEngine:
    """
    统一搜索引擎
    支持多种搜索引擎的聚合搜索
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化搜索引擎
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.max_results = config.get('max_results', 50)
        self.timeout = config.get('timeout', 30)
        self.retry_times = config.get('retry_times', 3)
        
        # 初始化各搜索引擎
        self.engines: Dict[str, BaseSearchEngine] = {}
        self._init_engines()
    
    def _init_engines(self) -> None:
        """初始化已配置的搜索引擎"""
        engines_config = self.config.get('engines', [])
        
        engine_map = {
            'google': GoogleSearchEngine,
            'bing': BingSearchEngine,
            'baidu': BaiduSearchEngine,
            'duckduckgo': DuckDuckGoEngine,
            'feishu': FeishuSearchEngine,
        }
        
        for engine_config in engines_config:
            name = engine_config.get('name', '').lower()
            enabled = engine_config.get('enabled', True)
            
            if enabled and name in engine_map:
                try:
                    self.engines[name] = engine_map[name](engine_config)
                    logger.info(f"已加载搜索引擎: {name}")
                except Exception as e:
                    logger.warning(f"加载搜索引擎 {name} 失败: {e}")
    
    def search(
        self,
        query: str,
        engines: Optional[List[str]] = None,
        max_results: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            engines: 使用的搜索引擎列表，None表示使用所有
            max_results: 最大结果数
            **kwargs: 其他参数
            
        Returns:
            搜索结果列表
        """
        if engines is None:
            engines = list(self.engines.keys())
        
        all_results = []
        
        for engine_name in engines:
            if engine_name not in self.engines:
                logger.warning(f"搜索引擎 {engine_name} 未加载")
                continue
            
            try:
                results = self._search_with_retry(
                    self.engines[engine_name],
                    query,
                    max_results,
                    **kwargs
                )
                all_results.extend(results)
            except Exception as e:
                logger.error(f"搜索引擎 {engine_name} 搜索失败: {e}")
        
        # 去重
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 按相关性排序
        unique_results.sort(
            key=lambda x: len(x.get('snippet', '')),
            reverse=True
        )
        
        return unique_results[:max_results]
    
    def _search_with_retry(
        self,
        engine: BaseSearchEngine,
        query: str,
        max_results: int,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """带重试的搜索"""
        for attempt in range(self.retry_times):
            try:
                return engine.search(query, max_results, **kwargs)
            except Exception as e:
                if attempt == self.retry_times - 1:
                    raise
                logger.warning(f"搜索重试 {attempt + 1}/{self.retry_times}: {e}")
        
        return []
    
    def search_by_topic(self, topic: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        按主题搜索
        自动生成相关搜索词
        
        Args:
            topic: 主题
            filters: 过滤条件
            
        Returns:
            搜索结果列表
        """
        # 生成相关搜索词
        search_queries = [
            topic,
            f"{topic} 最新",
            f"{topic} 官方",
            f"{topic} 规范",
            f"{topic} 标准",
        ]
        
        all_results = []
        for query in search_queries:
            results = self.search(query, max_results=10)
            all_results.extend(results)
        
        # 应用过滤
        if filters:
            all_results = self._apply_filters(all_results, filters)
        
        return all_results
    
    def _apply_filters(self, results: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """应用过滤条件"""
        filtered = []
        
        for result in results:
            # 按来源过滤
            if 'sources' in filters:
                if result.get('source') not in filters['sources']:
                    continue
            
            # 按文件类型过滤
            if 'file_types' in filters:
                url = result.get('url', '').lower()
                has_valid_type = any(
                    url.endswith(f".{ftype}") for ftype in filters['file_types']
                )
                if not has_valid_type:
                    continue
            
            # 排除关键词
            if 'exclude_keywords' in filters:
                text = (result.get('title', '') + result.get('snippet', '')).lower()
                if any(kw.lower() in text for kw in filters['exclude_keywords']):
                    continue
            
            filtered.append(result)
        
        return filtered
    
    def add_engine(self, name: str, engine: BaseSearchEngine) -> None:
        """
        添加自定义搜索引擎
        
        Args:
            name: 引擎名称
            engine: 搜索引擎实例
        """
        self.engines[name] = engine
    
    def remove_engine(self, name: str) -> bool:
        """
        移除搜索引擎
        
        Args:
            name: 引擎名称
            
        Returns:
            是否成功移除
        """
        if name in self.engines:
            del self.engines[name]
            return True
        return False
    
    def list_engines(self) -> List[str]:
        """列出所有可用的搜索引擎"""
        return list(self.engines.keys())
