# 数据安全合规监控平台 — 软件架构文档

> 版本：v1.0 | 日期：2026-04-17 | 维护者：飞天Claw

---

## 一、整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户层 (Feishu)                          │
│  单位画像 · 材料上传 · 关联信息归集 · 推送通知                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                       配置层 (config/)                          │
│  registry.yaml  总索引                                           │
│  global.yaml    全局配置（含scheduler节）                       │
│  levels/*.yaml  9个层级独立配置（L1-L7 / EDB / REF）           │
│  user_module.yaml  用户模块配置                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
┌─────────▼──────┐  ┌──────────▼──────┐  ┌────────▼─────────────┐
│  信息采集层     │  │  分析处理层      │  │  数据持久化层         │
│  engine/       │  │  engine/        │  │  persistence/        │
│                │  │                 │  │                      │
│ crawler_engine │  │ verification    │  │ bitable_manager      │
│ discovery_agent│  │ obligation_     │  │ local_backup        │
│ base_crawler   │  │   extractor     │  │ citation_graph_store│
│ crawlers/      │  │ applicability_  │  │                      │
│  ├─ cac       │  │   matcher       │  │                      │
│  ├─ samr      │  │                 │  │                      │
│  ├─ flk       │  │                 │  │                      │
│  └─ sector    │  │                 │  │                      │
└────────┬───────┘  └──────────┬─────┘  └────────┬─────────────┘
         │                     │                 │
         └─────────────────────┼─────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │          可视化 / 调度层          │
              │  visualization/  scheduler/      │
              │  citation_graph_app   job_scheduler│
              └─────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │           外部依赖              │
              │  飞书多维表格 · GitHub仓库     │
              │  CAC法规中心 · SAMR国家标准系统 │
              └─────────────────────────────────┘
```

---

## 二、目录结构

```
laws_regulations_monitor/
├── config/                          # 配置层
│   ├── registry.yaml                 # 总索引（9个层级的配置路径映射）
│   ├── global.yaml                   # 全局配置（飞书/GitHub/Scheduler）
│   ├── user_module.yaml              # 用户模块配置（app_token + table_id）
│   ├── hierarchy_levels.yaml          # 旧版合并配置（已部分废弃）
│   ├── data_sources.yaml             # 数据源配置（旧版）
│   └── levels/                       # 各层级独立配置
│       ├── l1_national_laws.yaml     # L1 国家法律
│       ├── l2_admin_regulations.yaml # L2 行政法规
│       ├── l3_department_rules.yaml  # L3 部门规章
│       ├── l4_national_standards.yaml# L4 国家标准
│       ├── l5_industry_standards.yaml# L5 行业标准
│       ├── l6_local_documents.yaml   # L6 地方文件
│       ├── l7_local_standards.yaml   # L7 地方标准
│       ├── edb_enforcement_cases.yaml# EDB 执法案例库
│       └── ref_reference_materials.yaml # REF 参考资料库
│
├── engine/                           # 分析处理层（核心业务逻辑）
│   ├── __init__.py
│   ├── base_crawler.py               # 爬虫抽象基类
│   ├── crawler_engine.py              # 配置驱动的通用爬虫引擎
│   ├── discovery_agent.py             # 探索Agent（持续发现新线索）
│   ├── verification.py                # 真实性验证引擎
│   ├── obligation_extractor.py        # 义务条款提取引擎
│   └── applicability_matcher.py       # 适用性匹配引擎
│
├── crawlers/                         # 各数据源专用爬虫
│   ├── __init__.py
│   ├── base_crawler.py               # 爬虫基类（与engine/base_crawler.py重复，待合并）
│   ├── cac_crawler.py                 # 网信办（CAC）JSON API爬虫
│   ├── samr_crawler.py               # SAMR国家标准系统爬虫
│   ├── flk_crawler.py                # 全国人大官网爬虫（flk = falvinkuai?）
│   └── sector_crawlers/              # 各部委垂直爬虫（工信/公安/金融/…）
│       └── __init__.py
│
├── persistence/                      # 数据持久化层
│   ├── __init__.py
│   ├── bitable_manager.py            # 飞书多表管理器（动态路由）
│   ├── local_backup.py               # 本地JSON备份（版本管理）
│   └── citation_graph_store.py       # 引用关系图谱存储
│
├── scheduler/                        # 任务调度层
│   ├── __init__.py
│   └── job_scheduler.py              # 三模式任务调度器
│
├── visualization/                    # 可视化层
│   └── citation_graph_app.py         # Plotly交互式引用关系图谱
│
├── bitable_client.py                 # 飞书多维表格底层API客户端
├── github_client.py                  # GitHub文件管理客户端
├── github_data_store.py              # GitHub JSON数据存储
├── source_manager.py                 # 数据源管理器
├── comparator.py                     # 对比器（旧版法规比对）
├── notifier.py                       # 通知推送模块
├── monitor.py                        # 监控入口（旧版）
├── integrated_monitor.py             # 集成监控入口（旧版）
├── cli.py                            # 命令行入口
├── run_monitor.py                    # 监控运行脚本
├── run_samr.py                      # SAMR单独运行脚本
└── scheduler.py                      # 旧版调度脚本
```

---

## 三、模块详解

### 3.1 配置层 `config/`

#### 3.1.1 registry.yaml — 总索引
| 字段 | 说明 |
|------|------|
| `levels` | 9个层级的配置路径、优先级、数据源状态、预估记录数 |
| `level_table_mapping` | 层级→飞书table_id 映射 |
| `bitable_app_token` | 飞书多维表格App Token |

#### 3.1.2 global.yaml — 全局配置
| 字段 | 说明 |
|------|------|
| `feishu` | app_id、app_secret |
| `github` | owner、repo、branch |
| `scheduler` | 运行模式(daily/manual/auto)、每日运行时间、探索间隔 |
| `storage` | 本地备份路径、GitHub存储开关 |

#### 3.1.3 levels/*.yaml — 9个层级独立配置
每个配置文件包含：

| 字段 | 说明 |
|------|------|
| `meta` | code、name、version、description |
| `fields` | 该层级独有的字段schema列表（字段名/类型/说明） |
| `sources` | 信息源列表（名称/URL/类型/api参数/status/keywords） |
| `crawl_params` | lookback_days、keywords、priority、file_types |
| `bitable` | table_name、field_mappings |

---

### 3.2 信息采集层 `engine/` + `crawlers/`

#### 3.2.1 crawler_engine.py — 配置驱动的通用爬虫引擎

**核心设计原则：** 引擎不认识任何层级，只认配置。

**功能：**
- 读取 `registry.yaml` 获取所有层级列表
- 遍历 `config/levels/*.yaml`，按配置执行爬取
- 支持4种爬取类型：`json_api` / `html_api` / `html` / `spa`
- 通用去重（基于标题+日期）
- 支持 `lookback_days` 和 `keywords` 参数
- 并发执行（ThreadPoolExecutor）

**核心接口：**
```python
class ConfigDrivenCrawlerEngine:
    def run_all(lookback_days=None) -> dict        # 运行全部层级
    def run_level(level_code: str) -> list          # 运行单个层级
    def crawl_source(source: dict) -> list          # 运行单个数据源
    def deduplicate(records: list) -> list          # 通用去重
```

#### 3.2.2 discovery_agent.py — 探索Agent

**功能：**
- 维护已搜索关键词集合，避免重复搜索
- 定期搜索立法动态、行业新闻（关键词池：含50+数据安全相关关键词）
- 探索微信公众号、行业论坛等非官方渠道
- 发现新线索后写入 `data/discovered_leads.json`
- 判断是否值得触发 crawler_engine 补爬（高优先级类型+权威来源+高置信关键词）
- 支持后台守护线程模式，定期自动探索

**核心接口：**
```python
class DiscoveryAgent:
    def search_new_leads() -> list          # 搜索新线索
    def should_crawl(lead: dict) -> bool   # 判断是否补爬
    def run_daemon(interval_hours=6)        # 后台守护
```

#### 3.2.3 base_crawler.py — 爬虫抽象基类

定义所有爬虫的接口规范：
```python
class BaseCrawler(ABC):
    @abstractmethod
    def crawl(self, config: dict, **kwargs) -> List[Dict]:
        pass
```

#### 3.2.4 crawlers/ — 各数据源专用爬虫

| 爬虫 | 数据源 | 接口类型 | 状态 |
|------|--------|---------|------|
| `cac_crawler.py` | 网信办 CAC 法规中心 | JSON API (channel_code) | ✅ 可用 |
| `samr_crawler.py` | SAMR 国家标准全文公开系统 | HTML API (POST关键词搜索) | ✅ 可用 |
| `flk_crawler.py` | 全国人大官网 | HTML 爬取 | 🔶 待测 |
| `sector_crawlers/` | 工信/公安/金融/卫健各部委 | HTML API / JSON | 🔶 待测 |

**CAC 爬虫支持的 Channel Codes：**
```
A09370301 = 法律（L1）
A09370302 = 行政法规（L2）
A09370303 = 部门规章（L3）
A09370304 = 司法解释
A09370305 = 规范性文件
A09370306 = 政策文件
A09370307 = 政策解读
```

---

### 3.3 分析处理层 `engine/`

#### 3.3.1 verification.py — 真实性验证引擎

**验证维度：**

| 维度 | 方法 | 可信度 |
|------|------|--------|
| 域名可信度 | gov.cn/cac.gov.cn/samr.gov.cn → high | 高 |
| 文件哈希校验 | SHA256 比对预期哈希值 | 高 |
| 版本一致性 | 检测"第X版/v1.0/2025年"等标记 | 中 |
| 内容一致性 | 标题与内容匹配度 | 中 |
| 敏感文件 | 含"内部/密级/机密" → pending_review | — |

**验证状态：** `verified` / `pending_review` / `unverified_content` / `expired`

**核心接口：**
```python
class VerificationResult:
    status: str       # verified/pending_review/unverified_content/expired
    domain_trust: str # high/medium/low
    hash_match: bool
    version_confirmed: bool
    content_consistent: bool
    is_sensitive: bool
    notes: str

def verify_document(url: str, content: bytes = None, expected_hash: str = None) -> VerificationResult
def check_domain_trust(url: str) -> str
def compute_hash(content: bytes) -> str
```

#### 3.3.2 obligation_extractor.py — 义务条款提取引擎

**义务类型分类：**

| 类型 | 关键词 | 标记色 |
|------|--------|--------|
| `must` | 应当、必须 | 🟠橙色 |
| `must_not` | 不得、禁止、严禁 | 🔴红色 |
| `may` | 可以、有权 | 🔵蓝色 |
| `punishment` | 罚款、责令、没收、情节严重 | 🟣紫色 |

**提取内容：**
- 条款编号（"第X条"）
- 义务内容（去噪后取前200字）
- 关键词列表
- 适用性信息（行业/规模/数据类型/地区）

**核心接口：**
```python
@dataclass
class Obligation:
    regulation_id: str
    article_number: str
    obligation_type: str   # must/must_not/may/punishment
    content: str
    keywords: List[str]
    applicability: dict    # {industries, scale, data_types, regions}

def extract_obligations(text: str, regulation_id: str) -> List[Obligation]
def classify_obligation_type(sentence: str) -> str
def extract_applicability(text: str) -> dict
def extract_article_number(text: str) -> str
```

#### 3.3.3 applicability_matcher.py — 适用性匹配引擎

**6维匹配：**

| # | 维度 | 匹配逻辑 |
|---|------|---------|
| 1 | 行业匹配 | 义务适用行业 ∩ 单位行业（宽松匹配） |
| 2 | 地域匹配 | 义务适用地区 ∩ 单位所在地 |
| 3 | 规模匹配 | 义务适用规模 ∩ 单位规模 |
| 4 | 数据类型 | 义务涉及数据类型 ∩ 单位数据类型 |
| 5 | 用户群体 | 未成年人用户 → 自动叠加未成年人保护法义务 |
| 6 | 跨境业务 | 有跨境 → 自动叠加数据出境合规义务 |

**核心接口：**
```python
def match_company_obligations(company_profile: dict, obligations: list) -> list
def get_special_obligations(company_profile: dict) -> List[Obligation]
```

**单位画像字段：**
```python
company_profile = {
    "industry": str,         # 行业
    "scale": str,            # 规模（大型/中型/小型）
    "province": str,          # 省份
    "city": str,              # 城市
    "data_types": list,      # 数据类型列表
    "user_groups": list,     # 用户群体（含"未成年人"触发特殊叠加）
    "cross_border": bool,    # 是否有跨境业务
}
```

**匹配结果示例：**
```json
{
  "obligation": Obligation(...),
  "match_score": "4/4",
  "match_reasons": ["行业匹配: ['互联网'] ∩ 互联网", "数据类型匹配: ...", ...],
  "applicability_level": "high"
}
```

---

### 3.4 数据持久化层 `persistence/`

#### 3.4.1 bitable_manager.py — 飞书多表管理器

**核心设计：** 通过 `registry.yaml` 动态获取层级→table_id 映射，无硬编码。

**功能：**
- 延迟加载：首次CRUD时自动将已有记录加载到内存缓存
- 通用去重：`deduplicate(table_id, key_field, new_records)` 基于内存缓存比对
- 动态路由：通过 `get_table_id(level_code)` 查询 registry.yaml

**核心接口：**
```python
class BitableManager:
    def write_record(table_id: str, fields: dict) -> str      # 写入单条
    def batch_write(table_id: str, records: list) -> list     # 批量写入（≤500条）
    def update_record(table_id: str, record_id: str, fields: dict)
    def delete_record(table_id: str, record_id: str)
    def query(table_id: str, filter: dict = None) -> list     # 查询
    def deduplicate(table_id: str, key_field: str, new_records: list) -> list
    def get_table_id(level_code: str) -> str                  # 动态获取
```

#### 3.4.2 local_backup.py — 本地JSON备份

**目录结构：**
```
data/backup/{level_code}/{date}/records.json
data/backup/{level_code}/latest -> 软链接指向最新版本
```

**功能：**
- 按日期版本化备份
- 自动更新 `latest` 软链接
- `diff(date1, date2)` 对比两版本差异（added/removed）
- `list_versions(level_code)` 列出所有历史版本

**核心接口：**
```python
class LocalBackup:
    def save_records(level_code: str, date: str, records: list) -> str
    def load_latest(level_code: str) -> list
    def list_versions(level_code: str) -> list
    def diff(level_code: str, date1: str, date2: str) -> dict
```

#### 3.4.3 citation_graph_store.py — 引用关系图谱存储

**关系类型：**

| 关系 | 说明 | 颜色 |
|------|------|------|
| `references` | 法规→标准引用 | 蓝 |
| `parent_child` | 上位法→下位法 | 橙 |
| `industry_to_national` | 行业标准→国家标准 | 红 |
| `supersedes` | 替代关系（旧→新） | 青 |
| `repeals` | 废止关系 | 粉 |

**核心接口：**
```python
class CitationGraphStore:
    def add_node(regulation_id: str, metadata: dict)    # 添加节点
    def add_edge(source: str, target: str, relation: str, description: str = "")
    def get_upstream(regulation_id: str) -> list         # 被谁引用
    def get_downstream(regulation_id: str) -> list      # 引用了谁
    def get_full_chain(regulation_id: str) -> dict       # BFS两层上下游
    def export_json() -> dict                            # 导出图谱JSON
    def save()                                           # 写入 data/citation_graph.json
```

---

### 3.5 任务调度层 `scheduler/`

#### 3.5.1 job_scheduler.py — 三模式任务调度器

| 模式 | 说明 | 场景 |
|------|------|------|
| `auto` | 每日定时爬取 + 探索Agent守护线程并行 | 生产环境推荐 |
| `scheduled` | 仅每日定时爬取（每分钟检查是否到点） | 轻量运行 |
| `manual` | 等待 API 触发（`trigger_run()` / `trigger_discovery()`） | 按需执行 |

**核心接口：**
```python
class JobScheduler:
    def run_daily()          # 每日定时任务
    def trigger_run()        # 手动触发爬取
    def trigger_discovery()  # 手动触发探索
    def run_daemon()         # 后台守护进程
```

**状态持久化：** 状态写入 `data/scheduler_state.json`，记录 last_run / last_discovery / 各层级最后运行时间。

---

### 3.6 可视化层 `visualization/`

#### 3.6.1 citation_graph_app.py — 引用关系图谱可视化

**技术选型：** Plotly（生成独立 HTML 文件，无需后端，可嵌入飞书）

**功能：**
- 节点大小 = `max(10, min(60, 10 + in_degree × 8))`（被引用越多节点越大）
- 5种关系类型用不同颜色区分
- 层级分组绘制（每层级一个 trace）
- Hover 显示完整信息（标题/层级/发文机关/状态/标签/被引次数）
- 内置 JS 支持：层级筛选按钮、法规名查询高亮
- 支持导出 PNG 图片

**输出：** `data/citation_graph.html`（18KB，可独立访问）

---

### 3.7 辅助模块

#### 3.7.1 github_client.py — GitHub文件管理客户端
- 将下载的法规文件同步到 data-collector 仓库
- 支持上传/下载/删除文件
- Token 从环境变量 `GITHUB_TOKEN` 读取

#### 3.7.2 github_data_store.py — GitHub JSON数据存储
- 将法规数据以 JSON 格式存储在 GitHub 仓库中
- 按层级组织：`data/laws/L1_国家法律.json` 等
- 不依赖飞书，可独立运行

#### 3.7.3 bitable_client.py — 飞书多维表格底层API客户端
- 封装飞书 Bitable v1 API
- 处理 access_token 自动刷新
- 提供原子化的 CRUD 操作

---

## 四、数据流全景

```
新规发现
    │
    ▼
discovery_agent 搜索线索 ──────────────────────────────────┐
    │                                                          │
    ▼                                                          │
crawler_engine 按配置爬取                                        │
    │                                                          │
    ├─── CAC JSON API ──────────────┐                         │
    ├─── SAMR HTML API ─────────────┼──► 原始数据              │
    └─── 其他来源 ──────────────────┘                         │
    │                                                          │
    ▼                                                          │
verification 真实性验证                                         │
    │                                                          │
    ├─── 域名可信度 ── high ─────────────────────────────┐     │
    ├─── 哈希校验 ── match ─────────────────────────────┤     │
    └─── 内容一致性 ── consistent ──────────────────────┘     │
    │                                                          │
    ▼                                                          │
obligation_extractor 义务条款提取                               │
    │                                                          │
    └─── must / must_not / may / punishment ──► 义务库         │
    │                                                          │
    ▼                                                          │
applicability_matcher 适用性匹配（按单位画像）                   │
    │                                                          │
    └─── 匹配的义务清单 ──► 飞书推送通知                        │
    │                                                          │
    ▼                                                          │
bitable_manager 写入飞书多维表格                                 │
    │                                                          │
    ▼                                                          │
local_backup 本地JSON备份                                        │
    │                                                          │
    ▼                                                          │
citation_graph_store 更新引用关系图谱 ──► 可视化HTML             │
```

---

## 五、9个层级说明

| 层级 | 代码 | 主要数据源 | 记录数估算 | 状态 |
|------|------|-----------|-----------|------|
| 国家法律 | L1 | CAC A09370301 / 全国人大 | ~15部 | ✅ 可用 |
| 行政法规 | L2 | CAC A09370302 | ~20部 | ✅ 可用 |
| 部门规章 | L3 | CAC A09370303+05 + 各部委 | ~60条 | ✅ 可用 |
| 国家标准 | L4 | SAMR HTML API | ~200条 | ✅ 可用 |
| 行业标准 | L5 | 金融/电信/公安/卫健各行业 | ~300条 | 🔶 待测 |
| 地方文件 | L6 | 各省市政府官网 | ~500条 | 🔶 待测 |
| 地方标准 | L7 | 省市监局标准信息服务平台 | ~200条 | 🔶 待测 |
| 执法案例库 | EDB | CAC/工信部/公安部/市监总局 | ~200条 | 🔶 待测 |
| 参考资料库 | REF | 信通院/电子标准院/赛博研究院 | ~100条 | 🔶 待测 |

---

## 六、已知问题与待办

### 待合并/清理
- [ ] `crawlers/base_crawler.py` 与 `engine/base_crawler.py` 重复，需合并
- [ ] `hierarchy_levels.yaml` 和 `data_sources.yaml` 为旧版合并配置，部分功能依赖它们，应逐步废弃
- [ ] `monitor.py` / `integrated_monitor.py` / `scheduler.py` 为旧版入口，应统一到新调度器

### 待完善
- [ ] L5-L7、EDB、REF 的爬虫实现（目前仅有配置，无实际爬虫代码）
- [ ] sector_crawlers/ 下各部委垂直爬虫
- [ ] 用户模块的飞书表尚未与主流程打通（仅创建了表结构）
- [ ] 探索Agent的搜索引擎接入（目前为框架预留）

### 沙箱限制
- 外部API（CAC、SAMR）在沙箱环境中DNS不通，需部署到有互联网的服务器验证
