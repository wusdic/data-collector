"""
DataCollector - 自动化资料收集与管理系统
=============================

自动化搜索、下载、分类、管理资料，支持定时更新提醒。
"""

__version__ = "1.0.0"
__author__ = "吴博"

from .core.search.engine import SearchEngine
from .core.downloader.download_manager import DownloadManager
from .core.classifier.classifier import Classifier
from .core.updater.update_monitor import UpdateMonitor
from .storage.database.db_manager import DatabaseManager
from .storage.file_manager.file_manager import FileManager

__all__ = [
    "SearchEngine",
    "DownloadManager", 
    "Classifier",
    "UpdateMonitor",
    "DatabaseManager",
    "FileManager",
]
