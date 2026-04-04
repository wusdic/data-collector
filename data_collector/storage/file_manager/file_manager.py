"""
文件管理器
管理下载文件的组织、分类、清理
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class FileManager:
    """
    文件管理器
    管理本地文件的组织、访问和清理
    """
    
    def __init__(self, base_dir: str = './data/files'):
        """
        初始化文件管理器
        
        Args:
            base_dir: 基础目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建默认目录结构
        self._init_directories()
        
        # 元数据文件
        self.metadata_file = self.base_dir / '.metadata.json'
        self._load_metadata()
    
    def _init_directories(self) -> None:
        """初始化目录结构"""
        self.directories = {
            'root': self.base_dir,
            'documents': self.base_dir / 'documents',
            'archives': self.base_dir / 'archives',
            'temp': self.base_dir / 'temp',
            'cache': self.base_dir / 'cache',
        }
        
        for name, path in self.directories.items():
            path.mkdir(parents=True, exist_ok=True)
    
    def _load_metadata(self) -> None:
        """加载元数据"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                'files': {},  # file_id -> metadata
                'folders': {},  # folder_id -> structure
                'tags': {},  # tag -> [file_ids]
                'deleted': [],  # 删除的文件记录
            }
    
    def _save_metadata(self) -> None:
        """保存元数据"""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
    
    def store(
        self,
        file_path: Path,
        category: str = 'documents',
        filename: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        存储文件
        
        Args:
            file_path: 源文件路径
            category: 分类
            filename: 自定义文件名
            tags: 标签
            metadata: 元数据
            
        Returns:
            文件信息
        """
        # 生成文件ID
        file_id = self._generate_file_id()
        
        # 确定目标路径
        category_dir = self.base_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
        
        # 确定文件名
        if filename is None:
            filename = file_path.name
        
        # 处理重名
        target_path = self._get_unique_path(category_dir / filename)
        
        # 复制文件
        shutil.copy2(file_path, target_path)
        
        # 收集文件信息
        stat = target_path.stat()
        
        file_info = {
            'id': file_id,
            'filename': target_path.name,
            'original_name': file_path.name,
            'path': str(target_path),
            'relative_path': str(target_path.relative_to(self.base_dir)),
            'category': category,
            'tags': tags or [],
            'size': stat.st_size,
            'size_mb': round(stat.st_size / 1024 / 1024, 2),
            'extension': target_path.suffix,
            'created_at': datetime.now().isoformat(),
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'metadata': metadata or {},
        }
        
        # 更新元数据
        self.metadata['files'][file_id] = file_info
        
        # 更新标签索引
        for tag in (tags or []):
            if tag not in self.metadata['tags']:
                self.metadata['tags'][tag] = []
            self.metadata['tags'][tag].append(file_id)
        
        self._save_metadata()
        
        logger.info(f"文件存储完成: {file_id} -> {target_path}")
        
        return file_info
    
    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        return self.metadata['files'].get(file_id)
    
    def get_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        """根据路径获取文件信息"""
        for file_info in self.metadata['files'].values():
            if file_info['path'] == path:
                return file_info
        return None
    
    def get_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """根据标签获取文件"""
        file_ids = self.metadata['tags'].get(tag, [])
        return [self.metadata['files'].get(fid) for fid in file_ids if fid in self.metadata['files']]
    
    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        """列出分类下的文件"""
        return [
            f for f in self.metadata['files'].values()
            if f['category'] == category
        ]
    
    def list_all(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """列出所有文件"""
        files = list(self.metadata['files'].values())
        
        if not include_deleted:
            files = [f for f in files if not f.get('deleted', False)]
        
        return files
    
    def update(self, file_id: str, updates: Dict[str, Any]) -> bool:
        """更新文件元数据"""
        if file_id not in self.metadata['files']:
            return False
        
        file_info = self.metadata['files'][file_id]
        
        # 处理标签更新
        if 'tags' in updates:
            old_tags = set(file_info.get('tags', []))
            new_tags = set(updates['tags'])
            
            # 移除旧标签索引
            for tag in old_tags - new_tags:
                if tag in self.metadata['tags']:
                    self.metadata['tags'][tag].remove(file_id)
            
            # 添加新标签索引
            for tag in new_tags - old_tags:
                if tag not in self.metadata['tags']:
                    self.metadata['tags'][tag] = []
                self.metadata['tags'][tag].append(file_id)
        
        file_info.update(updates)
        self._save_metadata()
        
        return True
    
    def move(self, file_id: str, new_category: str) -> bool:
        """移动文件到新分类"""
        if file_id not in self.metadata['files']:
            return False
        
        file_info = self.metadata['files'][file_id]
        old_path = Path(file_info['path'])
        new_path = self.base_dir / new_category / old_path.name
        
        # 确保新目录存在
        new_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 移动文件
        shutil.move(str(old_path), str(new_path))
        
        # 更新元数据
        file_info['path'] = str(new_path)
        file_info['relative_path'] = str(new_path.relative_to(self.base_dir))
        file_info['category'] = new_category
        
        self._save_metadata()
        
        return True
    
    def delete(self, file_id: str, permanent: bool = False) -> bool:
        """删除文件"""
        if file_id not in self.metadata['files']:
            return False
        
        file_info = self.metadata['files'][file_id]
        
        if permanent:
            # 永久删除
            path = Path(file_info['path'])
            if path.exists():
                path.unlink()
            
            # 从标签索引移除
            for tag in file_info.get('tags', []):
                if tag in self.metadata['tags']:
                    self.metadata['tags'][tag].remove(file_id)
            
            del self.metadata['files'][file_id]
        else:
            # 标记删除
            file_info['deleted'] = True
            file_info['deleted_at'] = datetime.now().isoformat()
            
            self.metadata['deleted'].append({
                'file_id': file_id,
                'deleted_at': file_info['deleted_at'],
            })
        
        self._save_metadata()
        
        return True
    
    def restore(self, file_id: str) -> bool:
        """恢复已删除文件"""
        if file_id not in self.metadata['files']:
            return False
        
        file_info = self.metadata['files'][file_id]
        
        if file_info.get('deleted'):
            file_info['deleted'] = False
            file_info.pop('deleted_at', None)
            
            # 从删除记录移除
            self.metadata['deleted'] = [
                d for d in self.metadata['deleted']
                if d['file_id'] != file_id
            ]
            
            self._save_metadata()
            return True
        
        return False
    
    def cleanup_temp(self, older_than_hours: int = 24) -> int:
        """
        清理临时目录
        
        Args:
            older_than_hours: 清理超过指定小时的临时文件
            
        Returns:
            清理的文件数
        """
        temp_dir = self.directories['temp']
        cutoff = datetime.now() - timedelta(hours=older_than_hours)
        cleaned = 0
        
        for path in temp_dir.iterdir():
            if path.is_file():
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                if mtime < cutoff:
                    path.unlink()
                    cleaned += 1
            elif path.is_dir():
                # 递归清理空目录
                try:
                    path.rmdir()
                    cleaned += 1
                except OSError:
                    pass
        
        logger.info(f"清理临时文件: {cleaned} 个")
        
        return cleaned
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计"""
        total_size = 0
        file_count = 0
        category_sizes = {}
        
        for file_info in self.metadata['files'].values():
            if not file_info.get('deleted'):
                total_size += file_info['size']
                file_count += 1
                
                cat = file_info['category']
                if cat not in category_sizes:
                    category_sizes[cat] = {'count': 0, 'size': 0}
                category_sizes[cat]['count'] += 1
                category_sizes[cat]['size'] += file_info['size']
        
        return {
            'total_files': file_count,
            'total_size': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'by_category': {
                cat: {
                    'count': data['count'],
                    'size_mb': round(data['size'] / 1024 / 1024, 2),
                }
                for cat, data in category_sizes.items()
            },
            'tags_count': len(self.metadata['tags']),
            'deleted_count': len(self.metadata['deleted']),
        }
    
    def _generate_file_id(self) -> str:
        """生成文件ID"""
        import uuid
        import hashlib
        
        # 使用 UUID + 时间戳
        unique = f"{uuid.uuid4()}{datetime.now().isoformat()}"
        return hashlib.md5(unique.encode()).hexdigest()[:12]
    
    def _get_unique_path(self, path: Path) -> Path:
        """获取唯一文件路径"""
        if not path.exists():
            return path
        
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
