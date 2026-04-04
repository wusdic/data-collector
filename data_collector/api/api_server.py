"""
REST API
提供 HTTP 接口供其他系统调用
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
import json

from flask import Flask, request, jsonify
from flask_cors import CORS

from ..core.search.engine import SearchEngine
from ..core.downloader.download_manager import DownloadManager
from ..core.classifier.classifier import Classifier
from ..core.updater.update_monitor import UpdateMonitor
from ..storage.database.db_manager import DatabaseManager
from ..storage.file_manager.file_manager import FileManager

logger = logging.getLogger(__name__)


class APIServer:
    """
    API 服务器
    基于 Flask 提供 REST API
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 API 服务器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.api_config = config.get('API', {})
        
        # 初始化 Flask
        self.app = Flask(__name__)
        CORS(self.app)
        
        # 初始化组件
        self._init_components(config)
        
        # 注册路由
        self._register_routes()
    
    def _init_components(self, config: Dict[str, Any]) -> None:
        """初始化组件"""
        try:
            self.search_engine = SearchEngine(config.get('SEARCH', {}))
            self.download_manager = DownloadManager(config.get('DOWNLOAD', {}))
            self.classifier = Classifier(config.get('CLASSIFIER', {}))
            self.updater = UpdateMonitor(config.get('UPDATER', {}))
            self.db_manager = DatabaseManager(config.get('DATABASE', {}))
            self.file_manager = FileManager()
            
            logger.info("API 组件初始化完成")
        except Exception as e:
            logger.error(f"API 组件初始化失败: {e}")
            raise
    
    def _register_routes(self) -> None:
        """注册路由"""
        # 健康检查
        self.app.add_url_rule('/health', 'health', self._health, methods=['GET'])
        
        # 搜索相关
        self.app.add_url_rule('/api/search', 'search', self._search, methods=['POST'])
        self.app.add_url_rule('/api/search/topic', 'search_topic', self._search_topic, methods=['POST'])
        
        # 下载相关
        self.app.add_url_rule('/api/download', 'download', self._download, methods=['POST'])
        self.app.add_url_rule('/api/download/batch', 'download_batch', self._download_batch, methods=['POST'])
        self.app.add_url_rule('/api/download/status', 'download_status', self._download_status, methods=['GET'])
        
        # 分类相关
        self.app.add_url_rule('/api/classify', 'classify', self._classify, methods=['POST'])
        self.app.add_url_rule('/api/categories', 'list_categories', self._list_categories, methods=['GET'])
        
        # 资源相关
        self.app.add_url_rule('/api/resources', 'list_resources', self._list_resources, methods=['GET'])
        self.app.add_url_rule('/api/resources/<int:resource_id>', 'get_resource', self._get_resource, methods=['GET'])
        self.app.add_url_rule('/api/resources/search', 'search_resources', self._search_resources, methods=['GET'])
        
        # 更新监控
        self.app.add_url_rule('/api/updater/check', 'check_updates', self._check_updates, methods=['POST'])
        self.app.add_url_rule('/api/updater/history', 'update_history', self._get_update_history, methods=['GET'])
        self.app.add_url_rule('/api/updater/sources', 'list_sources', self._list_sources, methods=['GET'])
        
        # 统计
        self.app.add_url_rule('/api/stats', 'get_stats', self._get_stats, methods=['GET'])
    
    def _require_auth(self) -> Optional[Dict[str, Any]]:
        """验证 API Key"""
        api_key = self.api_config.get('api_key')
        
        if not api_key:
            return None
        
        provided_key = request.headers.get('X-API-Key')
        
        if provided_key != api_key:
            return {'error': 'Unauthorized', 'code': 401}
        
        return None
    
    def _health(self) -> Dict[str, Any]:
        """健康检查"""
        return jsonify({
            'status': 'ok',
            'version': '1.0.0',
            'timestamp': self._get_timestamp(),
        })
    
    def _search(self) -> Dict[str, Any]:
        """搜索"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({'error': '缺少 query 参数', 'code': 400}), 400
        
        try:
            results = self.search_engine.search(
                query=data['query'],
                engines=data.get('engines'),
                max_results=data.get('max_results', 20)
            )
            
            return jsonify({
                'success': True,
                'query': data['query'],
                'count': len(results),
                'results': results,
            })
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _search_topic(self) -> Dict[str, Any]:
        """按主题搜索"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json()
        
        if not data or 'topic' not in data:
            return jsonify({'error': '缺少 topic 参数', 'code': 400}), 400
        
        try:
            results = self.search_engine.search_by_topic(
                topic=data['topic'],
                filters=data.get('filters')
            )
            
            return jsonify({
                'success': True,
                'topic': data['topic'],
                'count': len(results),
                'results': results,
            })
        except Exception as e:
            logger.error(f"主题搜索失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _download(self) -> Dict[str, Any]:
        """下载文件"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': '缺少 url 参数', 'code': 400}), 400
        
        try:
            local_path = self.download_manager.download(
                url=data['url'],
                filename=data.get('filename'),
                metadata=data.get('metadata')
            )
            
            return jsonify({
                'success': True,
                'url': data['url'],
                'local_path': local_path,
            })
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _download_batch(self) -> Dict[str, Any]:
        """批量下载"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({'error': '缺少 urls 参数', 'code': 400}), 400
        
        try:
            results = self.download_manager.download_batch(
                urls=data['urls'],
                filenames=data.get('filenames'),
                metadata_list=data.get('metadata_list')
            )
            
            return jsonify({
                'success': True,
                'total': len(data['urls']),
                'completed': sum(1 for r in results if r),
                'paths': results,
            })
        except Exception as e:
            logger.error(f"批量下载失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _download_status(self) -> Dict[str, Any]:
        """获取下载状态"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        stats = self.download_manager.get_statistics()
        return jsonify(stats)
    
    def _classify(self) -> Dict[str, Any]:
        """分类"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json()
        
        if not data or 'title' not in data:
            return jsonify({'error': '缺少 title 参数', 'code': 400}), 400
        
        try:
            result = self.classifier.classify(
                title=data['title'],
                content=data.get('content', ''),
                extension=data.get('extension', ''),
                url=data.get('url', '')
            )
            
            return jsonify({
                'success': True,
                'classification': result,
            })
        except Exception as e:
            logger.error(f"分类失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _list_categories(self) -> Dict[str, Any]:
        """列出分类"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        categories = self.classifier.list_categories()
        return jsonify({
            'success': True,
            'categories': categories,
        })
    
    def _list_resources(self) -> Dict[str, Any]:
        """列出资源"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        category = request.args.get('category')
        tags = request.args.getlist('tags')
        source = request.args.get('source')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        try:
            resources = self.db_manager.list_resources(
                category=category,
                tags=tags if tags else None,
                source=source,
                limit=limit,
                offset=offset
            )
            
            return jsonify({
                'success': True,
                'count': len(resources),
                'resources': resources,
            })
        except Exception as e:
            logger.error(f"列出资源失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _get_resource(self, resource_id: int) -> Dict[str, Any]:
        """获取资源"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        resource = self.db_manager.get_resource(resource_id)
        
        if not resource:
            return jsonify({'error': '资源不存在', 'code': 404}), 404
        
        return jsonify({
            'success': True,
            'resource': resource,
        })
    
    def _search_resources(self) -> Dict[str, Any]:
        """搜索资源"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        keyword = request.args.get('keyword')
        
        if not keyword:
            return jsonify({'error': '缺少 keyword 参数', 'code': 400}), 400
        
        try:
            resources = self.db_manager.search_resources(keyword)
            
            return jsonify({
                'success': True,
                'keyword': keyword,
                'count': len(resources),
                'resources': resources,
            })
        except Exception as e:
            logger.error(f"搜索资源失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _check_updates(self) -> Dict[str, Any]:
        """检查更新"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        data = request.get_json() or {}
        source_name = data.get('source')
        
        try:
            if source_name:
                updates = [self.updater.check_source(source_name)] if source_name else []
            else:
                updates = self.updater.check_all_sources()
            
            return jsonify({
                'success': True,
                'count': len(updates),
                'updates': [
                    {
                        'source': u.source_name,
                        'url': u.url,
                        'change_type': u.change_type,
                        'details': u.details,
                        'priority': u.priority,
                        'detected_at': u.detected_at.isoformat(),
                    }
                    for u in updates if u
                ],
            })
        except Exception as e:
            logger.error(f"检查更新失败: {e}")
            return jsonify({'error': str(e), 'code': 500}), 500
    
    def _get_update_history(self) -> Dict[str, Any]:
        """获取更新历史"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        source = request.args.get('source')
        limit = int(request.args.get('limit', 100))
        
        history = self.updater.get_update_history(source_name=source, limit=limit)
        
        return jsonify({
            'success': True,
            'count': len(history),
            'history': history,
        })
    
    def _list_sources(self) -> Dict[str, Any]:
        """列出数据源"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        sources = self.updater.get_source_status()
        
        return jsonify({
            'success': True,
            'sources': sources,
        })
    
    def _get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        auth_error = self._require_auth()
        if auth_error:
            return jsonify(auth_error)
        
        db_stats = self.db_manager.get_statistics()
        file_stats = self.file_manager.get_statistics()
        download_stats = self.download_manager.get_statistics()
        
        return jsonify({
            'success': True,
            'database': db_stats,
            'files': file_stats,
            'downloads': download_stats,
        })
    
    @staticmethod
    def _get_timestamp() -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def run(self, host: Optional[str] = None, port: Optional[int] = None, debug: bool = False) -> None:
        """
        启动服务器
        
        Args:
            host: 主机地址
            port: 端口
            debug: 调试模式
        """
        host = host or self.api_config.get('host', '0.0.0.0')
        port = port or self.api_config.get('port', 8080)
        debug = debug or self.api_config.get('debug', False)
        
        logger.info(f"启动 API 服务器: {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)
