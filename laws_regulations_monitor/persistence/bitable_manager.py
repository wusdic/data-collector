"""
persistence/bitable_manager.py
飞书多表管理器：通过 config/registry.yaml 动态映射层级→table_id
"""

import logging
import os
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://open.feishu.cn/open-apis/bitable/v1"


class BitableManager:
    """
    飞书多维表格管理器。
    通过 registry.yaml 动态获取 app_token 和 level→table_id 映射，无需硬编码。
    """

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base, "config", "registry.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            self.registry = yaml.safe_load(f)

        self.app_token = self.registry["bitable_app_token"]
        self.level_table_mapping: Dict[str, str] = self.registry["level_table_mapping"]
        self.level_names: Dict[str, str] = self.registry.get("level_names", {})

        # 复用已有的 BitableClient 逻辑获取 access_token
        self._access_token = self._get_access_token()
        self._headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        # 缓存：table_id → 已有的 record_id + 关键字段值
        self._cache: Dict[str, Dict[str, Dict]] = {}
        self._cache_loaded: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # access_token
    # ------------------------------------------------------------------
    def _get_access_token(self) -> str:
        token = os.environ.get("FEISHU_ACCESS_TOKEN", "")
        if token:
            return token

        app_id = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        if app_id and app_secret:
            try:
                resp = requests.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret},
                    timeout=10,
                )
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("tenant_access_token", "")
            except Exception as e:
                logger.error(f"获取 access_token 失败: {e}")

        logger.warning("未配置飞书 access_token，写入功能可能不可用")
        return ""

    # ------------------------------------------------------------------
    # table_id 路由
    # ------------------------------------------------------------------
    def get_table_id(self, level_code: str) -> str:
        """从 registry.yaml 动态获取层级对应的 table_id。"""
        table_id = self.level_table_mapping.get(level_code)
        if not table_id:
            raise ValueError(f"未知层级代码: {level_code}，请检查 registry.yaml")
        return table_id

    # ------------------------------------------------------------------
    # 内部 API
    # ------------------------------------------------------------------
    def _url(self, table_id: str, path: str = "") -> str:
        base = f"{API_BASE}/apps/{self.app_token}/tables/{table_id}/records"
        return base + (f"/{path}" if path else "")

    def _ensure_cache(self, table_id: str) -> None:
        """延迟加载：首次访问时抓取全量记录并建立索引。"""
        if self._cache_loaded.get(table_id):
            return
        self._cache[table_id] = {}
        if not self._access_token:
            logger.warning("无 access_token，跳过缓存加载")
            self._cache_loaded[table_id] = True
            return

        page_token = None
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            try:
                resp = requests.get(
                    self._url(table_id), headers=self._headers, params=params, timeout=30
                )
                data = resp.json()
                if data.get("code") != 0:
                    logger.error(f"加载记录失败: {data.get('msg')}")
                    break
                items = data.get("data", {}).get("items", [])
                for item in items:
                    fields = item.get("fields", {})
                    title = self._title_from(fields)
                    if title:
                        self._cache[table_id][title] = {
                            "record_id": item["record_id"],
                            "fields": fields,
                        }
                if not data.get("data", {}).get("has_more"):
                    break
                page_token = data.get("data", {}).get("page_token")
            except Exception as e:
                logger.error(f"请求失败: {e}")
                break

        self._cache_loaded[table_id] = True
        logger.info(f"缓存已加载 table={table_id}, 共 {len(self._cache[table_id])} 条")

    @staticmethod
    def _title_from(fields: Dict) -> str:
        """从 fields 中提取标题。"""
        for key in ("法规标题", "案例标题", "标题", "title"):
            val = fields.get(key, "")
            if isinstance(val, list) and val:
                return val[0].get("text", "") if isinstance(val[0], dict) else str(val[0])
            if val:
                return str(val)
        return ""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def write_record(self, table_id: str, fields: Dict) -> str:
        """
        写入单条记录。
        Returns: 新记录 ID
        """
        try:
            resp = requests.post(
                self._url(table_id),
                headers=self._headers,
                json={"fields": fields},
                timeout=30,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"write_record 失败: {data.get('msg')}")
            rid = data["data"]["record"]["record_id"]
            # 回写缓存
            title = self._title_from(fields)
            if title:
                self._ensure_cache(table_id)
                self._cache.setdefault(table_id, {})
                self._cache[table_id][title] = {"record_id": rid, "fields": fields}
            return rid
        except Exception as e:
            logger.error(f"write_record error: {e}")
            raise

    def batch_write(self, table_id: str, records: List[Dict]) -> List[str]:
        """
        批量写入记录（逐条，写入成功返回 record_id）。
        Returns: 写入成功的 record_id 列表
        """
        results = []
        for rec in records:
            try:
                rid = self.write_record(table_id, rec)
                results.append(rid)
            except Exception as e:
                logger.warning(f"batch_write 跳过: {e}")
        return results

    def update_record(self, table_id: str, record_id: str, fields: Dict) -> None:
        """更新指定记录。"""
        try:
            resp = requests.put(
                self._url(table_id, record_id),
                headers=self._headers,
                json={"fields": fields},
                timeout=30,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"update_record 失败: {data.get('msg')}")
            # 更新缓存
            title = self._title_from(fields)
            if title and table_id in self._cache:
                self._cache[table_id][title] = {
                    "record_id": record_id,
                    "fields": fields,
                }
        except Exception as e:
            logger.error(f"update_record error: {e}")
            raise

    def delete_record(self, table_id: str, record_id: str) -> None:
        """删除指定记录。"""
        try:
            resp = requests.delete(
                self._url(table_id, record_id),
                headers=self._headers,
                timeout=30,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"delete_record 失败: {data.get('msg')}")
            # 从缓存移除
            if table_id in self._cache:
                to_remove = [
                    k for k, v in self._cache[table_id].items()
                    if v.get("record_id") == record_id
                ]
                for k in to_remove:
                    del self._cache[table_id][k]
        except Exception as e:
            logger.error(f"delete_record error: {e}")
            raise

    def query(
        self, table_id: str, filter: Optional[Dict] = None, page_size: int = 500
    ) -> List[Dict]:
        """
        查询记录。可选 filter 条件（field_name / operator / value）。
        Returns: 飞书 record 列表（包含 record_id 和 fields）
        """
        self._ensure_cache(table_id)

        if filter is None:
            # 直接从缓存返回（已加载全量）
            return [
                {"record_id": v["record_id"], "fields": v["fields"]}
                for v in self._cache.get(table_id, {}).values()
            ]

        # 简单的字段过滤（内存执行）
        all_recs = self.query(table_id, page_size=page_size)
        conjunction = filter.get("conjunction", "and")
        conditions = filter.get("conditions", [])
        matched = []
        for rec in all_recs:
            fields = rec.get("fields", {})
            results = []
            for cond in conditions:
                fname = cond["field_name"]
                op = cond["operator"]
                val = cond["value"]
                actual = fields.get(fname, "")
                if op == "is":
                    ok = str(actual) == str(val[0]) if val else False
                elif op == "contains":
                    ok = str(val[0]) in str(actual)
                elif op == "isEmpty":
                    ok = not bool(actual)
                elif op == "isNotEmpty":
                    ok = bool(actual)
                else:
                    ok = False
                results.append(ok)
            keep = all(results) if conjunction == "and" else any(results)
            if keep:
                matched.append(rec)
        return matched

    def deduplicate(
        self, table_id: str, key_field: str, new_records: List[Dict]
    ) -> List[Dict]:
        """
        基于 key_field 去重，返回需要写入的新记录。
        - key_field 是新记录中的字段名（对应飞书的字段名）
        - 已存在于飞书表中的记录会被跳过
        """
        self._ensure_cache(table_id)
        cached = self._cache.get(table_id, {})
        existing_titles = set(cached.keys())

        unique = []
        seen = set()
        for rec in new_records:
            key_val = rec.get(key_field, "")
            if isinstance(key_val, list):
                key_val = key_val[0].get("text", "") if key_val else ""
            if not key_val:
                continue
            if key_val not in existing_titles and key_val not in seen:
                seen.add(key_val)
                unique.append(rec)

        return unique
