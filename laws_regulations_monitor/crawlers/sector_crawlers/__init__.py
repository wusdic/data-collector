"""
行业专项爬虫
各部委/行业主管部门的法规爬虫
"""

from .miit_crawler import MiitCrawler
from .tc260_crawler import TC260Crawler
from .pbc_crawler import PbcCrawler
from .nhc_crawler import NHCCrawler
from .nhsa_crawler import NhsaCrawler
from .mps_crawler import MpsCrawler
from .samr_reg_crawler import SamrRegCrawler

__all__ = [
    'MiitCrawler',
    'TC260Crawler',
    'PbcCrawler',
    'NhcCrawler',
    'NhsaCrawler',
    'MpsCrawler',
    'SamrRegCrawler',
]