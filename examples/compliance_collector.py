# 数据安全合规场景应用

本示例展示如何使用 DataCollector 构建数据安全合规资料库。

## 场景

企业需要持续跟踪数据安全、个人信息保护相关的法规政策变化，本工具可以自动：
1. 搜索最新法规政策
2. 下载法规全文
3. 自动分类归档
4. 监控更新并提醒

## 配置文件

```yaml
# config/compliance_config.yaml

SEARCH:
  engines:
    - name: baidu
      enabled: true
    - name: duckduckgo
      enabled: true

  max_results: 30
  timeout: 30

DOWNLOAD:
  download_dir: "./compliance_data/downloads"
  concurrent_downloads: 5

CLASSIFIER:
  categories:
    - name: 国家法律
      keywords: ["法律", "主席令", "全国人民代表大会"]
      extensions: ["pdf"]
    - name: 行政法规
      keywords: ["条例", "国务院令"]
      extensions: ["pdf"]
    - name: 部门规章
      keywords: ["规章", "部门规章", "办法", "规定", "规范"]
      extensions: ["pdf", "doc"]
    - name: 规范性文件
      keywords: ["通知", "意见", "指南", "指引", "公告"]
      extensions: ["pdf", "doc", "docx"]
    - name: 国家标准
      keywords: ["GB/T", "GB", "国家标准", "推荐性标准"]
      extensions: ["pdf"]
    - name: 行业标准
      keywords: ["行业标准", "行标", "JR/T", "GA/T"]
      extensions: ["pdf"]
    - name: 执法案例
      keywords: ["处罚", "通报", "典型案例", "违法"]
      extensions: ["pdf", "html"]

  auto_tags:
    - keyword: "数据安全"
      tag: "数据安全"
    - keyword: "个人信息"
      tag: "个人信息保护"
    - keyword: "隐私"
      tag: "隐私保护"
    - keyword: "网络安全"
      tag: "网络安全"
    - keyword: "等保"
      tag: "等级保护"
    - keyword: "数据跨境"
      tag: "数据跨境"
    - keyword: "数据分类分级"
      tag: "数据分类分级"

DATABASE:
  type: sqlite
  path: "./compliance_data/regulations.db"

UPDATER:
  enabled: true
  check_interval: 24
  sources:
    - name: 国家标准全文公开系统
      url: "https://open.samr.gov.cn/"
      enabled: true
    - name: 国家法律法规数据库
      url: "https://flk.npc.gov.cn/"
      enabled: true
    - name: 网信办
      url: "https://www.cac.gov.cn/"
      enabled: true
    - name: 公安部
      url: "https://www.mps.gov.cn/"
      enabled: true
    - name: 工信部
      url: "https://www.miit.gov.cn/"
      enabled: true
```

## 使用脚本

```python
#!/usr/bin/env python3
"""
数据安全合规资料收集脚本
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_collector import SearchEngine, DownloadManager, Classifier
from data_collector import UpdateMonitor, DatabaseManager
from data_collector.config import get_config
from data_collector.utils.logger import setup_logging

def main():
    # 设置日志
    setup_logging(level='INFO')
    
    # 加载配置
    config = get_config('config/compliance_config.yaml')
    
    # 初始化组件
    search_engine = SearchEngine(config.get('SEARCH', {}))
    download_manager = DownloadManager(config.get('DOWNLOAD', {}))
    classifier = Classifier(config.get('CLASSIFIER', {}))
    db_manager = DatabaseManager(config.get('DATABASE', {}))
    updater = UpdateMonitor(config.get('UPDATER', {}))
    
    # 定义收集任务
    tasks = [
        "数据安全法",
        "个人信息保护法",
        "网络安全法",
        "数据安全管理规范",
        "个人信息安全规范",
        "数据出境安全评估办法",
        "个人信息出境标准合同办法",
        "汽车数据安全管理若干规定",
        "工业数据分类分级指南",
        "金融数据安全分级指南",
    ]
    
    print("=" * 60)
    print("数据安全合规资料收集")
    print("=" * 60)
    
    all_results = []
    
    for task in tasks:
        print(f"\n处理: {task}")
        print("-" * 40)
        
        # 搜索
        results = search_engine.search(query=task, max_results=5)
        print(f"  找到 {len(results)} 条结果")
        
        for result in results:
            # 分类
            classification = classifier.classify(
                title=result.get('title', ''),
                content=result.get('snippet', ''),
                url=result.get('url', '')
            )
            
            result['classification'] = classification
            
            # 检查是否重复
            if classification.get('is_duplicate'):
                print(f"  ⏭️ 跳过重复: {result['title'][:40]}...")
                continue
            
            # 保存到数据库
            resource = {
                'title': result.get('title'),
                'url': result.get('url'),
                'source': result.get('source'),
                'category': classification.get('primary_category'),
                'tags': classification.get('tags'),
                'fingerprint': classification.get('fingerprint'),
            }
            
            resource_id = db_manager.save_resource(resource)
            result['resource_id'] = resource_id
            
            print(f"  ✅ 保存: {result['title'][:40]}... -> {classification.get('primary_category')}")
            
            all_results.append(result)
        
        # 添加指纹到分类器，避免后续重复
        for r in results:
            fp = r.get('classification', {}).get('fingerprint')
            if fp:
                classifier.add_fingerprint(fp)
    
    print("\n" + "=" * 60)
    print(f"收集完成! 共处理 {len(all_results)} 条资料")
    print("=" * 60)
    
    # 检查更新
    print("\n检查数据源更新...")
    updates = updater.check_all_sources()
    
    if updates:
        print(f"发现 {len(updates)} 个更新:")
        for update in updates:
            print(f"  - {update.source_name}: {update.change_type}")
        
        # 发送通知
        updater.notify_updates(updates)
    else:
        print("暂无更新")
    
    # 输出统计
    stats = db_manager.get_statistics()
    print("\n统计信息:")
    print(f"  总资源数: {stats.get('total_resources', 0)}")
    print(f"  本周新增: {stats.get('this_week', 0)}")

if __name__ == '__main__':
    main()
```

## 运行

```bash
# 初始化目录
mkdir -p compliance_data/downloads compliance_data/logs

# 运行收集脚本
python examples/compliance_collector.py

# 或者使用命令行
python main.py collect "数据安全法"
python main.py stats
```
