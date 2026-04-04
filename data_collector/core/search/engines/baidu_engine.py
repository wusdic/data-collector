"""
Baidu 搜索引擎
支持百度搜索
"""

import logging
import requests
from typing import List, Dict, Any

from ..engine import BaseSearchEngine

logger = logging.getLogger(__name__)


class BaiduSearchEngine(BaseSearchEngine):
    """百度搜索引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        self.search_url = config.get('search_url', '')
    
    def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        执行百度搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        results = []
        
        if self.api_key:
            results = self._search_api(query, max_results)
        else:
            results = self._search_scrape(query, max_results)
        
        return [self._normalize_result(r) for r in results]
    
    def _search_api(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """使用百度 API"""
        logger.info("百度 API 搜索")
        return []
    
    def _search_scrape(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """网页抓取方式"""
        results = []
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        params = {
            'wd': query,
            'rn': min(max_results, 20),
        }
        
        try:
            response = requests.get(
                'https://www.baidu.com/s',
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            # 使用正则解析结果
            import re
            pattern = r'<h3 class="t"><a[^>]*href="([^"]+)"[^>]*>([^<]*)</a></h3>'
            snippets_pattern = r'<div class="c-abstract"[^>]*>(.*?)</div>'
            
            matches = re.findall(pattern, response.text, re.DOTALL)
            snippets = re.findall(snippets_pattern, response.text, re.DOTALL)
            
            for i, (url, title) in enumerate(matches[:max_results]):
                # 清理 HTML 标签
                title_clean = re.sub(r'<[^>]+>', '', title)
                snippet = ''
                if i < len(snippets):
                    snippet = re.sub(r'<[^>]+>', '', snippets[i])[:200]
                
                results.append({
                    'title': title_clean,
                    'url': url,
                    'snippet': snippet,
                    'source': 'baidu',
                })
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
        
        return results
