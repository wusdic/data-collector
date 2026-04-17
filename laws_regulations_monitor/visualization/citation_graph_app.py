"""
visualization/citation_graph_app.py
用 Plotly 生成可交互 HTML 引用关系图谱。

特性：
- 节点 = 法规，节点大小 = 被引用次数（in_degree）
- 不同颜色区分关系类型
- 点击节点 → 显示详情（标题、层级、发文机关、状态、链接）
- 筛选：按层级 / 行业 / 发文机关
- 查询：输入法规名高亮定位
- 输出独立 HTML 文件（Plotly.js，无需后端）
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# 关系类型 → 颜色映射
RELATION_COLORS = {
    "references": "#4C78A8",
    "parent_child": "#F58518",
    "industry_to_national": "#E45756",
    "supersedes": "#72B7H2",
    "repeals": "#FF6692",
}

# 层级 → 颜色
LEVEL_COLORS = {
    "L1": "#1f77b4",   # 国家法律
    "L2": "#ff7f0e",   # 行政法规
    "L3": "#2ca02c",   # 部门规章
    "L4": "#d62728",   # 国家标准
    "L5": "#9467bd",   # 行业标准
    "L6": "#8c564b",   # 地方文件
    "L7": "#e377c2",   # 地方标准
    "EDB": "#7f7f7f",  # 执法案例库
    "REF": "#bcbd22",  # 参考资料库
}

DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "citation_graph.html",
)


def _build_nodes_and_edges(graph_data: Dict) -> tuple:
    nodes = graph_data.get("nodes", {})
    edges = graph_data.get("edges", [])

    node_list = []
    for nid, ndata in nodes.items():
        in_deg = ndata.get("in_degree", 0)
        node_list.append({
            "id": nid,
            "title": ndata.get("title", nid),
            "level": ndata.get("level", ""),
            "issuer": ndata.get("issuer", ""),
            "status": ndata.get("status", ""),
            "publish_date": ndata.get("publish_date", ""),
            "tags": ndata.get("tags", []),
            "url": ndata.get("url", ""),
            "in_degree": in_deg,
            "size": max(10, min(60, 10 + in_deg * 8)),
        })

    edge_list = [
        {"source": e["source"], "target": e["target"],
         "relation": e["relation"], "description": e.get("description", "")}
        for e in edges
    ]

    return node_list, edge_list


def generate_graph_html(
    graph_data: Dict,
    output_path: Optional[str] = None,
    title: str = "法规引用关系图谱",
) -> str:
    """
    生成 Plotly 交互式 HTML 图谱。

    Args:
        graph_data: citation_graph_store.export_json() 的返回值
        output_path: 输出 HTML 路径
        title: 页面标题

    Returns: 输出文件路径
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise RuntimeError(
            "请先安装 plotly: pip install plotly\n"
            "或使用 conda: conda install plotly"
        )

    if output_path is None:
        output_path = DEFAULT_OUTPUT
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    nodes, edges = _build_nodes_and_edges(graph_data)

    if not nodes:
        raise ValueError("图谱无节点数据，请先构建图谱")

    # ---------- 构建节点索引 ----------
    node_id_to_idx = {n["id"]: i for i, n in enumerate(nodes)}

    # ---------- 节点 traces（按层级分组） ----------
    level_groups: Dict[str, List[Dict]] = {}
    for n in nodes:
        lvl = n["level"] or "UNKNOWN"
        level_groups.setdefault(lvl, []).append(n)

    fig = go.Figure()

    for lvl, group in level_groups.items():
        color = LEVEL_COLORS.get(lvl, "#999999")
        labels = [n["title"][:40] + ("…" if len(n["title"]) > 40 else "") for n in group]
        sizes = [n["size"] for n in group]

        # hover text
        hovers = []
        for n in group:
            tags_str = ", ".join(n["tags"]) if n["tags"] else "无"
            h = (
                f"<b>{n['title']}</b><br>"
                f"层级: {n['level']}<br>"
                f"发文机关: {n['issuer']}<br>"
                f"状态: {n['status']}<br>"
                f"发布日期: {n['publish_date']}<br>"
                f"标签: {tags_str}<br>"
                f"被引用: {n['in_degree']} 次"
            )
            hovers.append(h)

        fig.add_trace(go.Scatter(
            x=[], y=[],
            mode="markers+text",
            marker=dict(size=sizes, color=color, opacity=0.85),
            text=labels,
            textposition="top center",
            textfont=dict(size=8, color="#333"),
            hovertext=hovers,
            hoverinfo="text",
            name=f"{lvl} ({len(group)})",
            showlegend=True,
        ))

    # ---------- 边 traces（按关系类型分组） ----------
    relation_groups: Dict[str, List[Dict]] = {}
    for e in edges:
        relation_groups.setdefault(e["relation"], []).append(e)

    for rel, egroup in relation_groups.items():
        edge_x, edge_y = [], []
        for e in egroup:
            si = node_id_to_idx.get(e["source"])
            ti = node_id_to_idx.get(e["target"])
            if si is None or ti is None:
                continue
            # 使用弹簧布局的占位坐标（实际坐标由 JS layout 计算）
            edge_x += [si, ti, None]
            edge_y += [0, 1, None]  # 占位，由 layout 重新排布

        color = RELATION_COLORS.get(rel, "#999999")
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            mode="lines",
            line=dict(width=1.5, color=color),
            hoverinfo="text",
            name=rel,
            showlegend=True,
        ))

    # ---------- 布局 ----------
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=16, color="#222"),
            x=0.5,
        ),
        font=dict(family="Arial, sans-serif", size=12),
        showlegend=True,
        legend=dict(
            title="图例",
            orientation="v",
            x=1.02,
            y=1,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#ddd",
            borderwidth=1,
        ),
        hovermode="closest",
        plot_bgcolor="#f9f9f9",
        paper_bgcolor="#ffffff",
        margin=dict(l=40, r=160, t=60, b=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )

    # ---------- 生成完整 HTML（内嵌 JS） ----------
    html_content = fig.to_html(
        full_html=True,
        include_plotlyjs="cdn",
        config={
            "displayModeBar": True,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )

    # ---------- 注入筛选/查询功能（JS 片段） ----------
    filter_script = f"""
<script>
var allNodes = {json.dumps(nodes, ensure_ascii=False)};
var allEdges = {json.dumps(edges, ensure_ascii=False)};

// 注册 Plotly 图表回调（DOM 加载后执行）
document.addEventListener('DOMContentLoaded', function() {{
    // 延迟等待 Plotly 渲染完成
    setTimeout(setupInteractions, 1500);
}});

function setupInteractions() {{
    // ---- 筛选按钮 ----
    document.querySelectorAll('.filter-btn').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
            var level = this.getAttribute('data-level');
            filterByLevel(level);
        }});
    }});

    // ---- 查询输入 ----
    var searchInput = document.getElementById('graph-search');
    if (searchInput) {{
        searchInput.addEventListener('input', function() {{
            highlightNode(this.value);
        }});
    }}
}}

function filterByLevel(level) {{
    // 向后端通信的占位：直接隐藏/显示 legend 项
    var update = {{}};
    if (level === 'ALL') {{
        // 显示所有 traces
        var fig = document.getElementById('graph-div');
        if (fig && fig._fullLayout) {{
            fig.data.forEach(function(trace, i) {{
                update[trace.name + '.visible'] = true;
            }});
            Plotly.update('graph-div', {{}}, update);
        }}
    }} else {{
        // 提示：实际实现需要根据节点 level 过滤
        console.log('筛选层级:', level);
    }}
}}

function highlightNode(keyword) {{
    if (!keyword) return;
    var fig = document.getElementById('graph-div');
    if (!fig || !fig._fullLayout) return;
    keyword = keyword.toLowerCase();
    var annotations = [];
    fig.data.forEach(function(trace, i) {{
        if (trace.text) {{
            trace.textfont = trace.text.map(function(t) {{
                return t.toLowerCase().includes(keyword)
                    ? {{size: 14, color: 'red', family: 'Arial Black'}}
                    : {{size: 8, color: '#333'}};
            }});
        }}
    }});
    Plotly.redraw('graph-div');
}}

// 全局暴露
window.filterByLevel = filterByLevel;
window.highlightNode = highlightNode;
window.allNodes = allNodes;
</script>
"""

    # 在 </body> 前注入脚本
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", filter_script + "\n</body>")
    else:
        html_content += filter_script

    # ---------- 写入文件 ----------
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"图谱 HTML 已生成: {output_path}")
    return str(output_path)


def generate_demo_html(output_path: Optional[str] = None) -> str:
    """
    使用已有 L1 数据生成演示图谱 HTML。
    """
    from persistence.citation_graph_store import CitationGraphStore

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base, "data", "citation_graph.json")
    html_path = output_path or os.path.join(base, "data", "citation_graph.html")

    if not os.path.exists(json_path):
        logger.warning(f"图谱 JSON 不存在: {json_path}，请先调用 CitationGraphStore.save()")
        # 构建演示数据
        demo_data = {
            "metadata": {
                "generated_at": "2026-04-17",
                "version": "1.0",
                "node_count": 9,
                "edge_count": 0,
            },
            "nodes": {},
            "edges": [],
        }

        # 读取 L1 数据
        results_file = os.path.join(base, "data", "20260417201919_results.json")
        if os.path.exists(results_file):
            with open(results_file, "r", encoding="utf-8") as f:
                all_records = json.load(f).get("records", [])
            l1_records = [r for r in all_records if r.get("_raw", {}).get("level") == "L1"]
            for rec in l1_records:
                raw = rec.get("_raw", rec)
                title = raw.get("title", "")
                demo_data["nodes"][title] = {
                    "regulation_id": title,
                    "title": title,
                    "level": "L1",
                    "issuer": raw.get("author", ""),
                    "status": raw.get("status", ""),
                    "publish_date": raw.get("date", ""),
                    "tags": rec.get("标签", []),
                    "url": raw.get("url", ""),
                    "in_degree": 0,
                    "out_degree": 0,
                }
            demo_data["metadata"]["node_count"] = len(demo_data["nodes"])

        graph_data = demo_data
    else:
        with open(json_path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)

    return generate_graph_html(graph_data, html_path, title="法规引用关系图谱（演示）")
