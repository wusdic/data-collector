# DataCollector

🛠️ **自动化资料收集与管理系统** - 搜索、下载、分类、管理、更新提醒，一站式解决方案。

## 功能特性

- 🔍 **多引擎搜索** - 支持 Google、Bing、百度、DuckDuckGo、飞书文档等多个搜索引擎
- 📥 **智能下载** - 多线程并发下载、自动重试、进度跟踪
- 🏷️ **自动分类** - 基于关键词的内容分类和标签生成
- 🔔 **更新监控** - 定期检查数据源变化，自动推送通知
- 💾 **统一存储** - SQLite 数据库 + 本地文件管理
- 🌐 **REST API** - 提供 HTTP 接口供其他系统调用
- 🔄 **去重检测** - 基于内容指纹的重复检测

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/wubo-ai/data-collector.git
cd data-collector

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 初始化

```bash
python main.py init
```

### 基础使用

```bash
# 搜索资料
python main.py search "数据安全 法律法规"

# 下载文件
python main.py download https://example.com/file.pdf

# 一站式收集（搜索+下载+分类+存储）
python main.py collect "个人信息保护法"

# 启动 API 服务
python main.py serve

# 查看统计
python main.py stats
```

## 配置说明

编辑 `config/default_config.yaml`:

```yaml
# 搜索配置
SEARCH:
  engines:
    - name: google
      enabled: true
      api_key: "YOUR_API_KEY"
      cx: "YOUR_CX"
  
  max_results: 50
  timeout: 30

# 下载配置
DOWNLOAD:
  download_dir: "./downloads"
  concurrent_downloads: 3
  max_file_size: 100  # MB

# 分类配置
CLASSIFIER:
  categories:
    - name: 法律法规
      keywords: ["法律", "法规", "条例"]
    - name: 技术标准
      keywords: ["标准", "规范", "GB"]

# 更新监控
UPDATER:
  enabled: true
  check_interval: 24  # 小时
  notify:
    - type: feishu
      enabled: true
      webhook: "YOUR_WEBHOOK"
```

## API 接口

启动服务后访问 `http://localhost:8080`:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/search` | 搜索资料 |
| POST | `/api/download` | 下载文件 |
| POST | `/api/classify` | 内容分类 |
| GET | `/api/resources` | 列出资源 |
| POST | `/api/updater/check` | 检查更新 |
| GET | `/api/stats` | 统计信息 |

### API 示例

```bash
# 搜索
curl -X POST http://localhost:8080/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "数据安全法", "max_results": 10}'

# 下载
curl -X POST http://localhost:8080/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/file.pdf"}'
```

## 项目结构

```
data-collector/
├── config/              # 配置文件
│   └── default_config.yaml
├── data_collector/       # 核心模块
│   ├── core/             # 核心功能
│   │   ├── search/       # 搜索引擎
│   │   ├── downloader/   # 下载器
│   │   ├── classifier/   # 分类器
│   │   └── updater/      # 更新监控
│   ├── storage/          # 存储层
│   │   ├── database/     # 数据库
│   │   └── file_manager/ # 文件管理
│   ├── api/              # REST API
│   └── utils/            # 工具函数
├── tests/               # 测试
├── examples/             # 示例
├── main.py              # 入口文件
├── requirements.txt
└── README.md
```

## 使用示例

### Python 代码调用

```python
from data_collector import SearchEngine, DownloadManager, Classifier
from data_collector.config import get_config

# 加载配置
config = get_config()

# 搜索
search_engine = SearchEngine(config['SEARCH'])
results = search_engine.search("数据安全 个人信息")

# 下载
downloader = DownloadManager(config['DOWNLOAD'])
path = downloader.download(results[0]['url'])

# 分类
classifier = Classifier(config['CLASSIFIER'])
result = classifier.classify(title="数据安全法全文", content="...")
print(f"分类: {result['primary_category']}")
print(f"标签: {result['tags']}")
```

### 与飞书集成

```python
from data_collector.integrations.feishu import feishu_search_doc_wiki

# 搜索飞书文档
results = feishu_search_doc_wiki(
    query="数据安全",
    doc_types=['DOC', 'BITABLE']
)
```

## 数据安全合规应用

本项目可应用于数据安全合规场景：

- 📜 **法规收集** - 自动收集数据安全、个人信息保护等相关法规
- 📊 **标准收集** - 收集 GB/T、ISO/IEC 等技术标准
- 📰 **政策追踪** - 监控法规政策更新
- 📚 **合规文档** - 构建企业合规文档库

## License

MIT License

## Contributing

欢迎提交 Issue 和 Pull Request！
