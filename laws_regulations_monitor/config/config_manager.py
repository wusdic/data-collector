"""
配置管理器 - 加载 YAML 配置
"""
import os
import yaml
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class Config:
    """数据源配置管理器"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._raw = self._load()
        self.global_config = self._raw.get('global', {})
        self.sources = self._parse_sources()

    def _load(self) -> Dict:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _parse_sources(self) -> List[Dict]:
        raw_sources = self._raw.get('sources', [])
        sources = []
        for src in raw_sources:
            # Merge global defaults
            merged = {
                'rate_limit': self.global_config.get('rate_limit_default', 2),
                'concurrent': self.global_config.get('concurrent_default', 3),
                'timeout': self.global_config.get('timeout', 15),
                'retry': self.global_config.get('retry', 3),
                'user_agent': self.global_config.get('user_agent'),
                'encoding': 'auto',
                **src
            }
            sources.append(merged)
        return sources

    def get_sources_by_level(self, level: str) -> List[Dict]:
        return [s for s in self.sources if level in s.get('levels', [])]

    def get_sources_by_status(self, status: str = 'active') -> List[Dict]:
        return [s for s in self.sources if s.get('status', 'active') == status]

    def get_working_sources(self) -> List[Dict]:
        """返回已知可用的数据源（已验证）"""
        working_ids = {'cac_l1', 'cac_l2', 'cac_l3', 'cac_law_interp', 'samr_standards'}
        return [s for s in self.sources if s['source_id'] in working_ids]

    def get_untested_sources(self) -> List[Dict]:
        """返回未验证的数据源"""
        untested_ids = {'miit_reg', 'pbc_reg', 'mps_reg', 'nhc_reg', 'mot_reg',
                       'moe_reg', 'samr_reg', 'miit_industry_std', 'tc260',
                       'local_std_beijing', 'local_std_shanghai',
                       'spc_interp', 'spp_interp', 'spp_cases', 'spc_cases',
                       'ncac_docs', 'cnist', 'gov_council'}
        return [s for s in self.sources if s['source_id'] in untested_ids]

    def get_blocked_sources(self) -> List[Dict]:
        """返回已知阻塞的数据源"""
        blocked_ids = {'npc_flk'}
        return [s for s in self.sources if s['source_id'] in blocked_ids]
