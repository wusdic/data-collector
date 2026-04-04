"""
数据库管理器
支持 SQLite、MySQL、PostgreSQL
"""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    数据库管理器
    提供统一的数据存储接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据库管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.db_type = config.get('type', 'sqlite')
        self.path = config.get('path', './data/collector.db')
        
        # 确保目录存在
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        
        # 连接池
        self._connection: Optional[sqlite3.Connection] = None
        
        # 初始化表结构
        self._init_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    @contextmanager
    def _cursor(self):
        """获取游标的上下文管理器"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_tables(self) -> None:
        """初始化数据表"""
        with self._cursor() as cursor:
            # 资源表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE,
                    source TEXT,
                    category TEXT,
                    tags TEXT,
                    fingerprint TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    file_type TEXT,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_checked TIMESTAMP,
                    is_favorite INTEGER DEFAULT 0,
                    is_deleted INTEGER DEFAULT 0
                )
            """)
            
            # 分类表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    keywords TEXT,
                    extensions TEXT,
                    parent_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (parent_id) REFERENCES categories(id)
                )
            """)
            
            # 标签表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 更新历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS update_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id INTEGER,
                    source_name TEXT,
                    url TEXT,
                    change_type TEXT,
                    details TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified INTEGER DEFAULT 0,
                    FOREIGN KEY (resource_id) REFERENCES resources(id)
                )
            """)
            
            # 搜索历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    engines TEXT,
                    results_count INTEGER,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 数据源表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT,
                    check_pattern TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_check TIMESTAMP,
                    last_hash TEXT,
                    check_interval INTEGER DEFAULT 24,
                    metadata TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_category ON resources(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_fingerprint ON resources(fingerprint)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_resources_created ON resources(created_at)")
            
            logger.info("数据库表初始化完成")
    
    # ============ 资源管理 ============
    
    def save_resource(self, resource: Dict[str, Any]) -> int:
        """
        保存资源
        
        Args:
            resource: 资源数据
            
        Returns:
            资源ID
        """
        with self._cursor() as cursor:
            # 处理 tags 和 metadata
            tags = json.dumps(resource.get('tags', []))
            metadata = json.dumps(resource.get('metadata', {}))
            
            cursor.execute("""
                INSERT OR REPLACE INTO resources 
                (title, url, source, category, tags, fingerprint, file_path, 
                 file_size, file_type, content, metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                resource.get('title'),
                resource.get('url'),
                resource.get('source'),
                resource.get('category'),
                tags,
                resource.get('fingerprint'),
                resource.get('file_path'),
                resource.get('file_size'),
                resource.get('file_type'),
                resource.get('content'),
                metadata,
            ))
            
            return cursor.lastrowid
    
    def get_resource(self, resource_id: int) -> Optional[Dict[str, Any]]:
        """获取资源"""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM resources WHERE id = ? AND is_deleted = 0", (resource_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_resource(row)
            return None
    
    def get_resource_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """根据 URL 获取资源"""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM resources WHERE url = ? AND is_deleted = 0", (url,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_resource(row)
            return None
    
    def get_resource_by_fingerprint(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """根据指纹获取资源"""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM resources WHERE fingerprint = ? AND is_deleted = 0", (fingerprint,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_resource(row)
            return None
    
    def list_resources(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出资源"""
        query = "SELECT * FROM resources WHERE is_deleted = 0"
        params = []
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self._cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [self._row_to_resource(row) for row in rows]
    
    def search_resources(
        self,
        keyword: str,
        fields: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """搜索资源"""
        fields = fields or ['title', 'content']
        
        conditions = ' OR '.join(f"{f} LIKE ?" for f in fields)
        params = [f"%{keyword}%"] * len(fields)
        
        query = f"""
            SELECT * FROM resources 
            WHERE is_deleted = 0 AND ({conditions})
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        with self._cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [self._row_to_resource(row) for row in rows]
    
    def update_resource(self, resource_id: int, updates: Dict[str, Any]) -> bool:
        """更新资源"""
        if not updates:
            return False
        
        sets = ', '.join(f"{k} = ?" for k in updates.keys())
        params = list(updates.values())
        params.append(resource_id)
        
        with self._cursor() as cursor:
            cursor.execute(
                f"UPDATE resources SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                params
            )
            return cursor.rowcount > 0
    
    def delete_resource(self, resource_id: int, permanent: bool = False) -> bool:
        """删除资源"""
        with self._cursor() as cursor:
            if permanent:
                cursor.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
            else:
                cursor.execute("UPDATE resources SET is_deleted = 1 WHERE id = ?", (resource_id,))
            
            return cursor.rowcount > 0
    
    def _row_to_resource(self, row: sqlite3.Row) -> Dict[str, Any]:
        """行转资源字典"""
        resource = dict(row)
        
        # 解析 JSON 字段
        if 'tags' in resource and resource['tags']:
            resource['tags'] = json.loads(resource['tags'])
        else:
            resource['tags'] = []
        
        if 'metadata' in resource and resource['metadata']:
            resource['metadata'] = json.loads(resource['metadata'])
        else:
            resource['metadata'] = {}
        
        return resource
    
    # ============ 分类管理 ============
    
    def save_category(self, category: Dict[str, Any]) -> int:
        """保存分类"""
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO categories (name, keywords, extensions, parent_id)
                VALUES (?, ?, ?, ?)
            """, (
                category['name'],
                json.dumps(category.get('keywords', [])),
                json.dumps(category.get('extensions', [])),
                category.get('parent_id'),
            ))
            
            return cursor.lastrowid
    
    def list_categories(self) -> List[Dict[str, Any]]:
        """列出所有分类"""
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM categories ORDER BY name")
            rows = cursor.fetchall()
            
            categories = []
            for row in rows:
                cat = dict(row)
                cat['keywords'] = json.loads(cat['keywords']) if cat['keywords'] else []
                cat['extensions'] = json.loads(cat['extensions']) if cat['extensions'] else []
                categories.append(cat)
            
            return categories
    
    # ============ 统计 ============
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._cursor() as cursor:
            stats = {}
            
            # 资源总数
            cursor.execute("SELECT COUNT(*) FROM resources WHERE is_deleted = 0")
            stats['total_resources'] = cursor.fetchone()[0]
            
            # 分类统计
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM resources 
                WHERE is_deleted = 0 AND category IS NOT NULL
                GROUP BY category
            """)
            stats['by_category'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 来源统计
            cursor.execute("""
                SELECT source, COUNT(*) as count 
                FROM resources 
                WHERE is_deleted = 0 AND source IS NOT NULL
                GROUP BY source
            """)
            stats['by_source'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 本周新增
            cursor.execute("""
                SELECT COUNT(*) FROM resources 
                WHERE is_deleted = 0 
                AND created_at >= datetime('now', '-7 days')
            """)
            stats['this_week'] = cursor.fetchone()[0]
            
            return stats
    
    def close(self) -> None:
        """关闭连接"""
        if self._connection:
            self._connection.close()
            self._connection = None
