"""
飞书文档搜索引擎
搜索飞书云空间和知识库文档
"""

import logging
from typing import List, Dict, Any, Optional

from ..engine import BaseSearchEngine

logger = logging.getLogger(__name__)


class FeishuSearchEngine(BaseSearchEngine):
    """飞书文档搜索引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.enabled = config.get('enabled', True)
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        doc_types: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        搜索飞书文档
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            doc_types: 文档类型过滤 ['DOC', 'SHEET', 'BITABLE', 'WIKI']
            
        Returns:
            搜索结果列表
        """
        try:
            # 导入飞书搜索工具
            from data_collector.integrations.feishu import feishu_search_doc_wiki
            
            results = feishu_search_doc_wiki(
                query=query,
                page_size=max_results,
                doc_types=doc_types
            )
            
            return [self._normalize_result(r) for r in results]
        except ImportError:
            logger.warning("飞书集成模块未安装")
            return []
        except Exception as e:
            logger.error(f"飞书搜索失败: {e}")
            return []
    
    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """标准化飞书搜索结果"""
        return {
            'title': result.get('title', ''),
            'url': result.get('url', result.get('doc_url', '')),
            'snippet': result.get('snippet', result.get('description', '')),
            'source': 'feishu',
            'doc_type': result.get('doc_type', 'DOC'),
            'owner': result.get('owner', {}).get('name', ''),
        }
