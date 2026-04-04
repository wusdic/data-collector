"""
Bing 搜索引擎
支持 Bing Search API
"""

import logging
import requests
from typing import List, Dict, Any

from ..engine import BaseSearchEngine

logger = logging.getLogger(__name__)


class BingSearchEngine(BaseSearchEngine):
    """Bing 搜索引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        self.search_url = config.get('search_url', '')
    
    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        执行 Bing 搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        if not self.api_key:
            logger.warning("Bing API Key 未配置")
            return []
        
        headers = {
            'Ocp-Apim-Subscription-Key': self.api_key,
        }
        
        params = {
            'q': query,
            'count': min(max_results, 50),
            'mkt': 'zh-CN',
            'safeSearch': 'Moderate',
        }
        
        try:
            response = requests.get(
                self.search_url,
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get('webPages', {}).get('value', []):
                results.append({
                    'title': item.get('name', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('snippet', ''),
                    'source': 'bing',
                })
            
            return [self._normalize_result(r) for r in results]
        except Exception as e:
            logger.error(f"Bing 搜索失败: {e}")
            return []
