"""
Google 搜索引警
支持 Google Custom Search API 和网页抓取
"""

import logging
import requests
from typing import List, Dict, Any

from ..engine import BaseSearchEngine

logger = logging.getLogger(__name__)


class GoogleSearchEngine(BaseSearchEngine):
    """Google 搜索引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        self.search_url = config.get('search_url', '')
        self.cx = config.get('cx', '')  # Custom Search Engine ID
    
    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        执行 Google 搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        results = []
        
        # 使用 API 搜索
        if self.api_key and self.cx:
            results = self._search_api(query, max_results)
        else:
            # 使用网页抓取
            results = self._search_scrape(query, max_results)
        
        return [self._normalize_result(r) for r in results]
    
    def _search_api(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """使用 Google Custom Search API"""
        results = []
        params = {
            'key': self.api_key,
            'cx': self.cx,
            'q': query,
            'num': min(max_results, 10),
        }
        
        try:
            response = requests.get(
                self.search_url,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            for item in data.get('items', []):
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'source': 'google',
                })
        except Exception as e:
            logger.error(f"Google API 搜索失败: {e}")
        
        return results
    
    def _search_scrape(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """网页抓取方式（备用）"""
        # 由于 Google 反爬虫较严格，这里提供备用方案
        logger.warning("Google 网页抓取模式不稳定，建议配置 API")
        return []
