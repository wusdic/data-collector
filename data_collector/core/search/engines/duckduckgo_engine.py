"""
DuckDuckGo 搜索引擎
免费无需 API Key
"""

import logging
import requests
from typing import List, Dict, Any

from ..engine import BaseSearchEngine

logger = logging.getLogger(__name__)


class DuckDuckGoEngine(BaseSearchEngine):
    """DuckDuckGo 搜索引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.search_url = config.get('search_url', 'https://duckduckgo.com/html/')
    
    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        执行 DuckDuckGo 搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        results = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        params = {
            'q': query,
            's': '0',  # 开始位置
        }
        
        try:
            # 获取第一页
            response = requests.get(
                self.search_url,
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            # 解析结果
            import re
            pattern = r'<a class="result__a" href="([^"]+)"[^>]*>([^<]*)</a>'
            snippet_pattern = r'<a class="result__snippet"[^>]*>(.*?)</a>'
            
            matches = re.findall(pattern, response.text, re.DOTALL)
            snippets = re.findall(snippet_pattern, response.text, re.DOTALL)
            
            for i, (url, title) in enumerate(matches[:max_results]):
                title_clean = re.sub(r'<[^>]+>', '', title)
                snippet = ''
                if i < len(snippets):
                    snippet = re.sub(r'<[^>]+>', '', snippets[i])[:200]
                
                results.append({
                    'title': title_clean,
                    'url': url,
                    'snippet': snippet,
                    'source': 'duckduckgo',
                })
        except Exception as e:
            logger.error(f"DuckDuckGo 搜索失败: {e}")
        
        return results
