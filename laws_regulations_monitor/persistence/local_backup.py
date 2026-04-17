"""
persistence/local_backup.py
本地 JSON 备份管理器。
目录结构：data/backup/{level_code}/{date}/records.json
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# 模块默认根目录
DEFAULT_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "backup")


class LocalBackup:
    """
    本地 JSON 备份管理器。

    目录结构：
        {base}/{level_code}/{date}/records.json
        {base}/{level_code}/latest -> 最新的 {date} 目录（软链接）
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base = Path(base_dir) if base_dir else Path(DEFAULT_BASE)
        self.base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 路径 helpers
    # ------------------------------------------------------------------
    def _backup_dir(self, level_code: str, date: str) -> Path:
        return self.base / level_code / date

    def _backup_file(self, level_code: str, date: str) -> Path:
        return self._backup_dir(level_code, date) / "records.json"

    def _latest_link(self, level_code: str) -> Path:
        return self.base / level_code / "latest"

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save_records(self, level_code: str, date: str, records: List[Dict]) -> str:
        """
        将 records 写入指定日期的 JSON 文件。
        Returns: 文件路径
        """
        dir_path = self._backup_dir(level_code, date)
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = self._backup_file(level_code, date)
        metadata = {
            "level_code": level_code,
            "date": date,
            "count": len(records),
            "saved_at": datetime.now().isoformat(),
            "records": records,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # 更新 latest 软链接
        latest = self._latest_link(level_code)
        date_path = Path(f"../../{level_code}/{date}")
        try:
            if latest.is_symlink():
                latest.unlink()
            latest.symlink_to(date_path, target_is_directory=True)
        except OSError as e:
            logger.warning(f"无法创建 latest 软链接: {e}")

        logger.info(f"已备份 [{level_code}/{date}] {len(records)} 条 → {file_path}")
        return str(file_path)

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def load_latest(self, level_code: str) -> List[Dict]:
        """
        加载指定层级的最新备份。
        Returns: records 列表（空列表表示无备份）
        """
        latest = self._latest_link(level_code)
        if not latest.is_symlink():
            # 尝试找目录下最晚的日期
            versions = self.list_versions(level_code)
            if not versions:
                logger.info(f"无备份记录: {level_code}")
                return []
            date = versions[-1]
        else:
            # 软链接指向相对路径 ../../{level_code}/{date}，需要拼接 base 来解析
            date = (self.base / latest.readlink()).resolve().parent.name  # 软链接指向的目录名即 date

        file_path = self._backup_file(level_code, date)
        if not file_path.exists():
            logger.warning(f"备份文件不存在: {file_path}")
            return []

        with open(file_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        logger.info(f"已加载最新备份 [{level_code}/{date}] {len(metadata.get('records', []))} 条")
        return metadata.get("records", [])

    # ------------------------------------------------------------------
    # 版本列表
    # ------------------------------------------------------------------
    def list_versions(self, level_code: str) -> List[str]:
        """
        列出指定层级的所有备份日期（倒序，最新在前）。
        """
        dir_path = self.base / level_code
        if not dir_path.is_dir():
            return []

        dates = [
            d.name for d in dir_path.iterdir()
            if d.is_dir() and d.name != "latest"
        ]
        dates.sort(reverse=True)
        return dates

    # ------------------------------------------------------------------
    # 对比差异
    # ------------------------------------------------------------------
    def diff(self, level_code: str, date1: str, date2: str) -> Dict[str, Any]:
        """
        对比两个日期版本的差异。
        Returns: {added: [...], removed: [...], unchanged: [...], stats: {...}}
        """
        f1 = self._backup_file(level_code, date1)
        f2 = self._backup_file(level_code, date2)

        def _load(path: Path) -> List[Dict]:
            if not path.exists():
                return []
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("records", [])

        def _keys(records: List[Dict]) -> set:
            return {r.get("法规标题") or r.get("title", "") for r in records}

        recs1 = _load(f1)
        recs2 = _load(f2)
        keys1 = _keys(recs1)
        keys2 = _keys(recs2)

        added = [r for r in recs2 if _keys([r]) <= keys2 - keys1]
        removed = [r for r in recs1 if _keys([r]) <= keys1 - keys2]

        return {
            "level_code": level_code,
            "date1": date1,
            "date2": date2,
            "count_date1": len(recs1),
            "count_date2": len(recs2),
            "added_count": len(added),
            "removed_count": len(removed),
            "added": added,
            "removed": removed,
            "stats": {
                "net_change": len(recs2) - len(recs1),
            },
        }
