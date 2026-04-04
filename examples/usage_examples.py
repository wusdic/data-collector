# DataCollector 使用示例

## 1. 基础搜索

```python
from data_collector import SearchEngine
from data_collector.config import get_config

config = get_config('config/default_config.yaml')
search_engine = SearchEngine(config['SEARCH'])

# 搜索
results = search_engine.search(
    query="数据安全法 个人信息保护",
    max_results=20
)

for r in results:
    print(f"标题: {r['title']}")
    print(f"链接: {r['url']}")
    print(f"摘要: {r['snippet']}")
    print("---")
```

## 2. 批量下载

```python
from data_collector import DownloadManager

downloader = DownloadManager({
    'download_dir': './downloads',
    'concurrent_downloads': 3,
    'max_file_size': 100,
    'retry_times': 3,
})

urls = [
    'https://example.com/doc1.pdf',
    'https://example.com/doc2.pdf',
    'https://example.com/doc3.pdf',
]

paths = downloader.download_batch(urls)
print(f"下载完成: {len(paths)} 个文件")
```

## 3. 内容分类

```python
from data_collector import Classifier

classifier = Classifier({
    'categories': [
        {
            'name': '法律法规',
            'keywords': ['法律', '法规', '条例', '办法', '规定'],
            'extensions': ['pdf', 'doc']
        },
        {
            'name': '技术标准',
            'keywords': ['标准', '规范', 'GB', 'ISO'],
            'extensions': ['pdf', 'doc']
        }
    ],
    'auto_tags': [
        {'keyword': '数据安全', 'tag': '数据安全'},
        {'keyword': '个人信息', 'tag': '隐私保护'}
    ]
})

result = classifier.classify(
    title="《数据安全法》全文",
    content="为了规范数据处理活动，保障数据安全，促进数据开发利用...",
    url="https://example.com/law.pdf"
)

print(f"主分类: {result['primary_category']}")
print(f"所有匹配: {result['categories']}")
print(f"标签: {result['tags']}")
print(f"是否重复: {result['is_duplicate']}")
```

## 4. 一站式收集

```python
from data_collector.core.search.engine import SearchEngine
from data_collector.core.downloader.download_manager import DownloadManager
from data_collector.core.classifier.classifier import Classifier
from data_collector.storage.database.db_manager import DatabaseManager

# 初始化组件
search_engine = SearchEngine(config['SEARCH'])
downloader = DownloadManager(config['DOWNLOAD'])
classifier = Classifier(config['CLASSIFIER'])
db = DatabaseManager(config['DATABASE'])

# 一站式收集
query = "数据安全合规"
max_results = 10

# 1. 搜索
results = search_engine.search(query, max_results=max_results)

# 2. 下载
urls = [r['url'] for r in results]
paths = downloader.download_batch(urls)

# 3. 分类并存储
for result, path in zip(results, paths):
    # 分类
    classification = classifier.classify(
        title=result['title'],
        content=result['snippet']
    )
    
    # 存储
    resource = {
        'title': result['title'],
        'url': result['url'],
        'source': result['source'],
        'category': classification['primary_category'],
        'tags': classification['tags'],
        'fingerprint': classification['fingerprint'],
        'file_path': path,
    }
    
    db.save_resource(resource)

print(f"收集完成: {len(results)} 条资料")
```

## 5. 更新监控

```python
from data_collector import UpdateMonitor

monitor = UpdateMonitor({
    'enabled': True,
    'check_interval': 24,
    'sources': [
        {
            'name': '国家标准全文公开',
            'url': 'https://open.samr.gov.cn/',
            'enabled': True,
        },
        {
            'name': '法律法规数据库',
            'url': 'https://flk.npc.gov.cn/',
            'enabled': True,
        }
    ],
    'notify': [
        {
            'type': 'feishu',
            'enabled': True,
            'webhook': 'YOUR_WEBHOOK_URL'
        }
    ]
})

# 检查所有数据源
updates = monitor.check_all_sources()

if updates:
    monitor.notify_updates(updates)
    print(f"发现 {len(updates)} 个更新")
else:
    print("暂无更新")
```

## 6. API 服务使用

```python
from data_collector.api.api_server import APIServer
from data_collector.config import get_config

config = get_config()
api = APIServer(config.get_all())

# 启动服务
api.run(host='0.0.0.0', port=8080)
```

### API 调用示例

```bash
# 搜索
curl -X POST http://localhost:8080/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "数据安全法", "max_results": 10}'

# 下载
curl -X POST http://localhost:8080/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/file.pdf"}'

# 分类
curl -X POST http://localhost:8080/api/classify \
  -H "Content-Type: application/json" \
  -d '{"title": "数据安全法全文", "content": "为了规范数据处理活动..."}'

# 列出资源
curl http://localhost:8080/api/resources?category=法律法规

# 统计
curl http://localhost:8080/api/stats
```
