"""
DataCollector 测试
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestClassifier:
    """分类器测试"""
    
    def setup_method(self):
        """测试前准备"""
        from data_collector.core.classifier.classifier import Classifier
        
        self.classifier = Classifier({
            'categories': [
                {
                    'name': '法律法规',
                    'keywords': ['法律', '法规', '条例', '办法'],
                    'extensions': ['pdf', 'doc']
                },
                {
                    'name': '技术标准',
                    'keywords': ['标准', '规范', 'GB', 'ISO'],
                    'extensions': ['pdf']
                }
            ],
            'auto_tags': [
                {'keyword': '数据安全', 'tag': '数据安全'}
            ]
        })
    
    def test_classify_law(self):
        """测试法律分类"""
        result = self.classifier.classify(
            title="《数据安全法》全文",
            content="为了规范数据处理活动，保障数据安全..."
        )
        
        assert result['primary_category'] == '法律法规'
        assert '数据安全' in result['tags']
    
    def test_classify_standard(self):
        """测试标准分类"""
        result = self.classifier.classify(
            title="GB/T 35273-2020 信息安全技术",
            content="本标准规定了个人信息安全规范..."
        )
        
        assert result['primary_category'] == '技术标准'
    
    def test_fingerprint(self):
        """测试指纹生成"""
        result1 = self.classifier.classify(
            title="数据安全法",
            content="为了规范数据处理活动"
        )
        
        result2 = self.classifier.classify(
            title="数据安全法",
            content="为了规范数据处理活动"
        )
        
        assert result1['fingerprint'] == result2['fingerprint']
        assert result2['is_duplicate'] == True


class TestDownloadManager:
    """下载管理器测试"""
    
    def setup_method(self):
        """测试前准备"""
        from data_collector.core.downloader.download_manager import DownloadManager
        import tempfile
        
        self.temp_dir = Path(tempfile.mkdtemp())
        
        self.downloader = DownloadManager({
            'download_dir': str(self.temp_dir),
            'concurrent_downloads': 2,
            'max_file_size': 10,
            'retry_times': 1,
            'supported_types': ['pdf', 'txt']
        })
    
    def test_extract_filename(self):
        """测试文件名提取"""
        from data_collector.core.downloader.download_manager import DownloadTask
        
        task = DownloadTask('https://example.com/path/document.pdf')
        assert task.filename == 'document.pdf'
    
    def test_statistics(self):
        """测试统计"""
        stats = self.downloader.get_statistics()
        
        assert 'total' in stats
        assert 'completed' in stats
        assert stats['total'] == 0


class TestDatabaseManager:
    """数据库管理器测试"""
    
    def setup_method(self):
        """测试前准备"""
        from data_collector.storage.database.db_manager import DatabaseManager
        import tempfile
        
        self.temp_db = Path(tempfile.mktemp(suffix='.db'))
        
        self.db = DatabaseManager({
            'type': 'sqlite',
            'path': str(self.temp_db)
        })
    
    def teardown_method(self):
        """测试后清理"""
        self.db.close()
        if self.temp_db.exists():
            self.temp_db.unlink()
    
    def test_save_resource(self):
        """测试保存资源"""
        resource = {
            'title': '测试文档',
            'url': 'https://example.com/doc.pdf',
            'source': 'test',
            'category': '测试分类'
        }
        
        resource_id = self.db.save_resource(resource)
        assert resource_id > 0
    
    def test_get_resource(self):
        """测试获取资源"""
        resource = {
            'title': '测试文档',
            'url': 'https://example.com/doc.pdf',
        }
        
        resource_id = self.db.save_resource(resource)
        retrieved = self.db.get_resource(resource_id)
        
        assert retrieved is not None
        assert retrieved['title'] == '测试文档'
    
    def test_list_resources(self):
        """测试列出资源"""
        # 保存多个资源
        for i in range(3):
            self.db.save_resource({
                'title': f'文档{i}',
                'url': f'https://example.com/doc{i}.pdf',
                'category': '测试'
            })
        
        resources = self.db.list_resources(category='测试')
        assert len(resources) >= 3


class TestSearchEngine:
    """搜索引擎测试"""
    
    def setup_method(self):
        """测试前准备"""
        from data_collector.core.search.engine import SearchEngine
        
        self.engine = SearchEngine({
            'max_results': 10,
            'timeout': 30,
            'engines': [
                {'name': 'duckduckgo', 'enabled': True}
            ]
        })
    
    def test_list_engines(self):
        """测试列出引擎"""
        engines = self.engine.list_engines()
        assert 'duckduckgo' in engines


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
