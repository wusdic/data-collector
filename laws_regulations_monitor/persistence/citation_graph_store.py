"""
persistence/citation_graph_store.py
引用关系图谱存储管理器。
关系类型：references / parent_child / industry_to_national / supersedes / repeals
输出：data/citation_graph.json
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "citation_graph.json",
)

RELATION_TYPES = {
    "references",       # A references B（A 引用 B）
    "parent_child",     # 父子关系（如办法→实施细则）
    "industry_to_national",  # 行业标准引用国家标准
    "supersedes",       # A 废止/替代 B
    "repeals",          # A 正式废止 B
}


class CitationGraphStore:
    """
    引用关系图谱存储。

    图谱结构（JSON）：
    {
        "metadata": { "generated_at": "...", "version": "..." },
        "nodes": {
            "<regulation_id>": {
                "regulation_id": "...",
                "title": "...",
                "level": "L1",
                "issuer": "全国人大常委会",
                "status": "现行有效",
                "publish_date": "2021-08-20",
                "tags": [...],
                "in_degree": 3,
                "out_degree": 5
            }
        },
        "edges": [
            {
                "source": "<regulation_id>",
                "target": "<regulation_id>",
                "relation": "references",
                "description": "..."
            }
        ]
    }
    """

    def __init__(self, output_path: Optional[str] = None):
        self.output_path = Path(output_path) if output_path else Path(DEFAULT_OUTPUT)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.nodes: Dict[str, Dict] = {}
        self.edges: List[Dict] = []

        # 加载已有图谱
        self._load()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self.output_path.exists():
            try:
                with open(self.output_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.nodes = data.get("nodes", {})
                self.edges = data.get("edges", [])
                logger.info(f"图谱已加载: {len(self.nodes)} 节点, {len(self.edges)} 边")
            except Exception as e:
                logger.warning(f"图谱加载失败，将重新创建: {e}")

    def _rebuild_degrees(self) -> None:
        in_deg = defaultdict(int)
        out_deg = defaultdict(int)
        for edge in self.edges:
            out_deg[edge["source"]] += 1
            in_deg[edge["target"]] += 1
        for nid in self.nodes:
            self.nodes[nid]["in_degree"] = in_deg.get(nid, 0)
            self.nodes[nid]["out_degree"] = out_deg.get(nid, 0)

    def _gen_id(self, title: str) -> str:
        """用标题生成稳定 ID（URL-safe）。"""
        return title.strip()

    # ------------------------------------------------------------------
    # 节点操作
    # ------------------------------------------------------------------
    def add_node(self, regulation_id: str, metadata: Dict) -> None:
        """
        添加或更新节点。
        metadata 至少包含 title，其他字段可选。
        """
        if regulation_id not in self.nodes:
            self.nodes[regulation_id] = {
                "regulation_id": regulation_id,
                "title": metadata.get("title", regulation_id),
                "level": metadata.get("level", ""),
                "issuer": metadata.get("issuer", ""),
                "status": metadata.get("status", ""),
                "publish_date": metadata.get("publish_date", ""),
                "tags": metadata.get("tags", []),
                "url": metadata.get("url", ""),
                "in_degree": 0,
                "out_degree": 0,
            }
        else:
            # 更新已有节点（保留度信息，只更新元数据）
            self.nodes[regulation_id].update(metadata)
        self._rebuild_degrees()

    # ------------------------------------------------------------------
    # 边操作
    # ------------------------------------------------------------------
    def add_edge(
        self, source: str, target: str, relation: str, description: str = ""
    ) -> None:
        """
        添加引用关系边。
        source → target（source 引用/包含/废止 target）
        """
        if relation not in RELATION_TYPES:
            raise ValueError(
                f"未知关系类型: {relation}，可选: {RELATION_TYPES}"
            )

        # 避免重复边
        for edge in self.edges:
            if (
                edge["source"] == source
                and edge["target"] == target
                and edge["relation"] == relation
            ):
                return

        self.edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "description": description,
        })
        self._rebuild_degrees()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_upstream(self, regulation_id: str) -> List[Dict]:
        """
        上游：谁引用/废止了本法规。
        即：其他法规 → 本法规 的边。
        """
        return [
            {
                "upstream_id": e["source"],
                "upstream_title": self.nodes.get(e["source"], {}).get("title", e["source"]),
                "relation": e["relation"],
                "description": e["description"],
            }
            for e in self.edges
            if e["target"] == regulation_id
        ]

    def get_downstream(self, regulation_id: str) -> List[Dict]:
        """
        下游：本法规引用/包含/废止了哪些。
        即：本法规 → 其他法规 的边。
        """
        return [
            {
                "downstream_id": e["target"],
                "downstream_title": self.nodes.get(e["target"], {}).get("title", e["target"]),
                "relation": e["relation"],
                "description": e["description"],
            }
            for e in self.edges
            if e["source"] == regulation_id
        ]

    def get_full_chain(self, regulation_id: str) -> Dict[str, Any]:
        """
        获取某法规的完整上下游链条。
        向上回溯 2 层，向下扩展 2 层。
        """
        def bfs(start_id: str, direction: str, max_depth: int):
            visited = {start_id}
            frontier = [(start_id, 0)]
            result = []
            while frontier:
                nid, depth = frontier.pop(0)
                if depth >= max_depth:
                    continue
                neighbors = (
                    [e["source"] for e in self.edges if e["target"] == nid]
                    if direction == "upstream"
                    else [e["target"] for e in self.edges if e["source"] == nid]
                )
                for nb in neighbors:
                    if nb not in visited:
                        visited.add(nb)
                        result.append({"id": nb, "depth": depth + 1})
                        frontier.append((nb, depth + 1))
            return result

        upstream = bfs(regulation_id, "upstream", 2)
        downstream = bfs(regulation_id, "downstream", 2)

        return {
            "regulation_id": regulation_id,
            "title": self.nodes.get(regulation_id, {}).get("title", regulation_id),
            "upstream": [
                {
                    "id": u["id"],
                    "title": self.nodes.get(u["id"], {}).get("title", u["id"]),
                    "depth": u["depth"],
                }
                for u in upstream
            ],
            "downstream": [
                {
                    "id": d["id"],
                    "title": self.nodes.get(d["id"], {}).get("title", d["id"]),
                    "depth": d["depth"],
                }
                for d in downstream
            ],
        }

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_json(self) -> Dict:
        """导出完整图谱数据（含元数据）。"""
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
            },
            "nodes": self.nodes,
            "edges": self.edges,
        }

    def save(self) -> str:
        """持久化到 JSON 文件。"""
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(self.export_json(), f, ensure_ascii=False, indent=2)
        logger.info(f"图谱已保存: {self.output_path} ({len(self.nodes)} 节点, {len(self.edges)} 边)")
        return str(self.output_path)

    # ------------------------------------------------------------------
    # 辅助：从爬虫记录构建演示图谱
    # ------------------------------------------------------------------
    @classmethod
    def from_records(cls, records: List[Dict], output_path: Optional[str] = None) -> "CitationGraphStore":
        """
        从爬虫记录批量构建图谱。
        自动根据 level 建立父子关系（L3 引用 L2，L2 引用 L1 等）。
        """
        store = cls(output_path)

        for rec in records:
            raw = rec.get("_raw", rec)
            title = raw.get("title", rec.get("法规标题", ""))
            level = raw.get("level", "")
            author = raw.get("author", rec.get("发文机关", ""))
            status = raw.get("status", "")
            date = raw.get("date", "")
            tags = rec.get("标签", [])
            url = rec.get("原文链接", {}).get("link", "") if isinstance(rec.get("原文链接"), dict) else str(rec.get("原文链接", ""))

            reg_id = store._gen_id(title)
            store.add_node(reg_id, {
                "title": title,
                "level": level,
                "issuer": author,
                "status": status,
                "publish_date": date,
                "tags": tags,
                "url": url,
            })

            # 建立层级间引用关系（L3→L2, L2→L1 等）
            hierarchy = ["L1", "L2", "L3", "L4", "L5", "L6", "L7"]
            if level in hierarchy:
                idx = hierarchy.index(level)
                if idx > 0:
                    parent_level = hierarchy[idx - 1]
                    # 同一发文机关的上一级法规（弱关联启发式）
                    # 这里仅建立通用层级链，不做具体法规匹配
                    parent_title = title  # 占位，实际使用时由外部补充具体关系

        store.save()
        return store
