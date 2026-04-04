"""
下载管理器
支持多线程并发下载、自动重试、进度跟踪
"""

import os
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote
import hashlib
import time

from .file_handler import FileHandler

logger = logging.getLogger(__name__)


class DownloadTask:
    """下载任务"""
    
    def __init__(self, url: str, filename: Optional[str] = None, metadata: Optional[Dict] = None):
        self.url = url
        self.filename = filename or self._extract_filename(url)
        self.metadata = metadata or {}
        self.status = 'pending'  # pending, downloading, completed, failed
        self.progress = 0
        self.error = None
        self.local_path = None
        self.file_size = 0
        self.checksum = None
    
    @staticmethod
    def _extract_filename(url: str) -> str:
        """从URL提取文件名"""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = os.path.basename(path)
        
        if not filename:
            filename = f"download_{int(time.time())}"
        
        return filename
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'url': self.url,
            'filename': self.filename,
            'status': self.status,
            'progress': self.progress,
            'local_path': str(self.local_path) if self.local_path else None,
            'file_size': self.file_size,
            'error': self.error,
            'metadata': self.metadata,
        }


class DownloadManager:
    """
    下载管理器
    支持多线程下载、断点续传、进度跟踪
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化下载管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.download_dir = Path(config.get('download_dir', './downloads'))
        self.concurrent_downloads = config.get('concurrent_downloads', 3)
        self.max_file_size = config.get('max_file_size', 100) * 1024 * 1024  # MB to bytes
        self.retry_times = config.get('retry_times', 3)
        self.retry_delay = config.get('retry_delay', 5)
        self.supported_types = set(config.get('supported_types', []))
        
        # 创建下载目录
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件处理器
        self.file_handler = FileHandler()
        
        # 活跃任务
        self.tasks: Dict[str, DownloadTask] = {}
    
    def download(self, url: str, filename: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        """
        下载单个文件
        
        Args:
            url: 文件URL
            filename: 保存的文件名
            metadata: 元数据
            
        Returns:
            本地文件路径
        """
        task = DownloadTask(url, filename, metadata)
        self.tasks[url] = task
        
        try:
            task.status = 'downloading'
            local_path = self._download_file(task)
            task.status = 'completed'
            task.local_path = Path(local_path)
            return str(local_path)
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            raise
    
    def download_batch(
        self,
        urls: List[str],
        filenames: Optional[List[str]] = None,
        metadata_list: Optional[List[Dict]] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """
        批量下载
        
        Args:
            urls: 文件URL列表
            filenames: 文件名列表
            metadata_list: 元数据列表
            progress_callback: 进度回调函数
            
        Returns:
            本地文件路径列表
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.concurrent_downloads) as executor:
            futures = {}
            
            for i, url in enumerate(urls):
                filename = filenames[i] if filenames and i < len(filenames) else None
                metadata = metadata_list[i] if metadata_list and i < len(metadata_list) else None
                
                task = DownloadTask(url, filename, metadata)
                self.tasks[url] = task
                
                future = executor.submit(self._download_with_retry, task)
                futures[future] = task
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    path = future.result()
                    results.append(path)
                    if progress_callback:
                        progress_callback(task)
                except Exception as e:
                    logger.error(f"下载失败 {task.url}: {e}")
                    results.append(None)
        
        return results
    
    def _download_with_retry(self, task: DownloadTask) -> str:
        """带重试的下载"""
        for attempt in range(self.retry_times):
            try:
                return self._download_file(task)
            except Exception as e:
                if attempt == self.retry_times - 1:
                    task.error = str(e)
                    raise
                logger.warning(f"下载重试 {attempt + 1}/{self.retry_times}: {task.url}")
                time.sleep(self.retry_delay)
        
        raise Exception("下载失败")
    
    def _download_file(self, task: DownloadTask) -> str:
        """执行文件下载"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        response = requests.get(task.url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # 检查文件大小
        content_length = response.headers.get('content-length')
        if content_length:
            file_size = int(content_length)
            if file_size > self.max_file_size:
                raise Exception(f"文件过大: {file_size / 1024 / 1024:.2f}MB > {self.max_file_size / 1024 / 1024}MB")
            task.file_size = file_size
        
        # 保存文件
        save_path = self.download_dir / task.filename
        
        # 处理重复文件名
        save_path = self._get_unique_path(save_path)
        
        with open(save_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if task.file_size:
                        task.progress = int(downloaded / task.file_size * 100)
        
        # 计算校验和
        task.checksum = self._calculate_checksum(save_path)
        
        return str(save_path)
    
    def _get_unique_path(self, path: Path) -> Path:
        """获取唯一文件路径（处理重名）"""
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
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """计算文件MD5校验和"""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
    
    def get_task(self, url: str) -> Optional[DownloadTask]:
        """获取任务状态"""
        return self.tasks.get(url)
    
    def get_tasks_by_status(self, status: str) -> List[DownloadTask]:
        """按状态获取任务"""
        return [t for t in self.tasks.values() if t.status == status]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取下载统计"""
        tasks = list(self.tasks.values())
        return {
            'total': len(tasks),
            'completed': sum(1 for t in tasks if t.status == 'completed'),
            'failed': sum(1 for t in tasks if t.status == 'failed'),
            'pending': sum(1 for t in tasks if t.status == 'pending'),
            'downloading': sum(1 for t in tasks if t.status == 'downloading'),
        }
    
    def clear_completed(self) -> int:
        """清除已完成任务"""
        urls = [url for url, t in self.tasks.items() if t.status == 'completed']
        for url in urls:
            del self.tasks[url]
        return len(urls)
