"""
爬虫子包
包含各政府数据源的专项爬虫
"""

from engine.base_crawler import BaseCrawler
from .flk_crawler import FLKCrawler
from .samr_crawler import SAMRCrawler
from .cac_crawler import CACCrawler
from .edb_crawler import EdbCrawler
from .ref_crawler import RefCrawler

__all__ = [
    'BaseCrawler',
    'FLKCrawler',
    'SAMRCrawler',
    'CACCrawler',
    'EdbCrawler',
    'RefCrawler',
]
