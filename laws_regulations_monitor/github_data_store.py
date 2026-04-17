"""
GitHub JSON 数据文件存储
将法规数据以 JSON 格式存储在 GitHub 仓库中，按层级组织
"""

import os
import json
import logging
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GitHubDataStore:
    """GitHub JSON 数据文件存储（不依赖飞书）"""

    # 层级名称映射
    LEVEL_NAMES = {
        'L1': 'L1-国家法律',
        'L2': 'L2-行政法规',
        'L3': 'L3-部门文件',
        'L4': 'L4-国家标准',
        'L5': 'L5-行业标准',
        'L6': 'L6-地方文件',
        'L7': 'L7-地方标准',
        'case': '执法案例库',
    }

    # 层级到目录路径的映射
    LEVEL_DIRS = {
        'L1': 'data/laws/L1_国家法律.json',
        'L2': 'data/laws/L2_行政法规.json',
        'L3': 'data/laws/L3_部门文件.json',
        'L4': 'data/laws/L4_国家标准.json',
        'L5': 'data/laws/L5_行业标准.json',
        'L6': 'data/laws/L6_地方文件.json',
        'L7': 'data/laws/L7_地方标准.json',
        'case': 'data/cases/执法案例库.json',
    }

    API_BASE = "https://api.github.com"

    def __init__(self, github_client, config: Dict[str, Any]):
        self.github = github_client
        self.data_dir = config.get('data_dir', 'data')
        
        self.session = github_client.session

    def _get_json_path(self, level: str) -> str:
        """获取指定层级的 JSON 文件路径"""
        return self.LEVEL_DIRS.get(level, f'data/{level}.json')

    def _get_level_name(self, level: str) -> str:
        """获取层级显示名称"""
        return self.LEVEL_NAMES.get(level, level)

    def load_level_data(self, level: str) -> Dict[str, Any]:
        """
        从 GitHub 加载某层级的 JSON 数据文件
        
        Args:
            level: 层级标识 (L1-L7, case)
            
        Returns:
            JSON 数据字典，包含 records 列表
        """
        path = self._get_json_path(level)
        
        exists, content = self._read_file(path)
        
        if not exists:
            # 文件不存在，返回空数据结构
            logger.info(f"[{level}] JSON 文件不存在，将创建新文件")
            return self._create_empty_data(level)
        
        try:
            data = json.loads(content)
            logger.info(f"[{level}] 已加载 {len(data.get('records', []))} 条记录")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"[{level}] JSON 解析失败: {e}")
            return self._create_empty_data(level)

    def _create_empty_data(self, level: str) -> Dict[str, Any]:
        """创建空的 JSON 数据结构"""
        return {
            'level': level,
            'level_name': self._get_level_name(level),
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_count': 0,
            'github_data_dir': self._get_json_path(level).replace('.json', ''),
            'records': []
        }

    def _read_file(self, path: str) -> tuple:
        """
        从 GitHub 读取文件内容
        
        Returns:
            (exists: bool, content: str or None)
        """
        url = f"{self.API_BASE}/repos/{self.github.owner}/{self.github.repo}/contents/{path}"
        params = {'ref': self.github.branch}
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                content = base64.b64decode(data['content']).decode('utf-8')
                return True, content
            elif resp.status_code == 404:
                return False, None
            else:
                logger.warning(f"读取文件失败 [{path}]: HTTP {resp.status_code}")
                return False, None
        except Exception as e:
            logger.error(f"读取文件异常 [{path}]: {e}")
            return False, None

    def _write_file(self, path: str, content: str, commit_message: str) -> bool:
        """
        写入文件到 GitHub
        
        Args:
            path: 文件路径
            content: 文件内容 (JSON 字符串)
            commit_message: 提交信息
            
        Returns:
            是否成功
        """
        url = f"{self.API_BASE}/repos/{self.github.owner}/{self.github.repo}/contents/{path}"
        
        # 检查文件是否已存在
        exists = False
        sha = None
        if exists:
            _, existing = self._read_file(path)
            if existing:
                sha = existing.get('sha')
        
        # 先检查文件是否存在
        check_url = f"{self.API_BASE}/repos/{self.github.owner}/{self.github.repo}/contents/{path}"
        params = {'ref': self.github.branch}
        try:
            resp = self.session.get(check_url, params=params, timeout=15)
            if resp.status_code == 200:
                exists = True
                sha = resp.json().get('sha')
        except:
            pass
        
        payload = {
            'message': commit_message,
            'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            'branch': self.github.branch,
        }
        
        if sha:
            payload['sha'] = sha
        
        try:
            resp = self.session.put(url, json=payload, timeout=30)
            if resp.status_code in (200, 201):
                logger.info(f"文件写入成功: {path}")
                return True
            else:
                error = resp.json().get('message', f"HTTP {resp.status_code}")
                logger.error(f"文件写入失败 [{path}]: {error}")
                return False
        except Exception as e:
            logger.error(f"文件写入异常 [{path}]: {e}")
            return False

    def save_level_data(self, level: str, data: Dict, commit_message: str = None) -> bool:
        """
        保存某层级的 JSON 数据文件到 GitHub
        
        Args:
            level: 层级标识
            data: 要保存的完整数据（包含 records 列表）
            commit_message: 提交信息
            
        Returns:
            是否成功
        """
        path = self._get_json_path(level)
        
        if commit_message is None:
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            count = len(data.get('records', []))
            commit_message = f"[自动更新] {now} - {self._get_level_name(level)} ({count} 条)"
        
        # 更新 last_updated 时间戳
        data['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        data['total_count'] = len(data.get('records', []))
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        
        return self._write_file(path, content, commit_message)

    def append_records(self, level: str, new_records: List[Dict]) -> Dict[str, Any]:
        """
        追加新记录到指定层级的 JSON 文件
        
        Args:
            level: 层级标识
            new_records: 要追加的新记录列表
            
        Returns:
            {appended_count, skipped_count, total_count, errors}
        """
        if not new_records:
            return {'appended_count': 0, 'skipped_count': 0, 'total_count': 0, 'errors': []}
        
        # 加载现有数据
        data = self.load_level_data(level)
        
        existing_ids = {rec.get('id') for rec in data.get('records', []) if rec.get('id')}
        existing_titles = {self._normalize_title(rec.get('title', '')) for rec in data.get('records', [])}
        existing_urls = {rec.get('url', '') for rec in data.get('records', []) if rec.get('url')}
        existing_doc_numbers = {rec.get('doc_number', '') for rec in data.get('records', []) if rec.get('doc_number')}
        
        appended = 0
        skipped = 0
        errors = []
        
        for record in new_records:
            try:
                # 生成唯一 ID
                record_id = self._generate_record_id(record)
                record['id'] = record_id
                record['crawled_at'] = datetime.utcnow().isoformat() + 'Z'
                record['level'] = level
                
                # 去重检查
                norm_title = self._normalize_title(record.get('title', ''))
                
                if record_id in existing_ids:
                    skipped += 1
                    continue
                if norm_title in existing_titles:
                    skipped += 1
                    continue
                if record.get('url') and record['url'] in existing_urls:
                    skipped += 1
                    continue
                if record.get('doc_number') and record['doc_number'] in existing_doc_numbers:
                    skipped += 1
                    continue
                
                data['records'].append(record)
                existing_ids.add(record_id)
                existing_titles.add(norm_title)
                if record.get('url'):
                    existing_urls.add(record['url'])
                if record.get('doc_number'):
                    existing_doc_numbers.add(record['doc_number'])
                
                appended += 1
                
            except Exception as e:
                errors.append({'title': record.get('title', '?'), 'error': str(e)})
                logger.error(f"处理记录失败 [{record.get('title', '?')}]: {e}")
        
        # 保存更新后的数据
        if appended > 0:
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            commit_message = f"[自动更新] {now} - 新增 {appended} 条{self._get_level_name(level)}"
            self.save_level_data(level, data, commit_message)
        
        result = {
            'appended_count': appended,
            'skipped_count': skipped,
            'total_count': len(data.get('records', [])),
            'errors': errors
        }
        
        logger.info(f"[{level}] 追加结果: 新增 {appended}, 跳过 {skipped}, 总计 {result['total_count']}")
        
        return result

    def _normalize_title(self, title: str) -> str:
        """标准化标题（用于去重比对）"""
        import re
        if not title:
            return ''
        # 去除括号内的公告号等
        title = re.sub(r'[\[【\(（].*?[\]】\)）]', '', title)
        # 去除首尾空格
        title = title.strip()
        # 统一全角括号
        title = title.replace('（', '(').replace('）', ')')
        return title.lower()

    def _generate_record_id(self, record: Dict) -> str:
        """生成记录唯一 ID（基于标题+URL 的 MD5）"""
        import hashlib
        title = record.get('title', '')
        url = record.get('url', '')
        doc_number = record.get('doc_number', '')
        
        key = f"{title}|{url}|{doc_number}"
        return hashlib.md5(key.encode('utf-8')).hexdigest()[:16]

    def get_all_records(self, level: str) -> List[Dict]:
        """
        获取某层级的所有记录（去重后）
        
        Args:
            level: 层级标识
            
        Returns:
            记录列表
        """
        data = self.load_level_data(level)
        return data.get('records', [])

    def update_metadata(self, level: str, stats: Dict) -> bool:
        """
        更新 metadata/last_updated.json
        
        Args:
            level: 层级标识
            stats: 统计信息
            
        Returns:
            是否成功
        """
        metadata_path = f"{self.data_dir}/metadata/last_updated.json"
        
        # 读取现有 metadata
        exists, content = self._read_file(metadata_path)
        
        if exists and content:
            try:
                metadata = json.loads(content)
            except:
                metadata = {}
        else:
            metadata = {'levels': {}}
        
        # 更新指定层级的统计
        if 'levels' not in metadata:
            metadata['levels'] = {}
        
        metadata['levels'][level] = {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_count': stats.get('total_count', 0),
            'appended_count': stats.get('appended_count', 0),
            'skipped_count': stats.get('skipped_count', 0),
        }
        
        metadata['last_sync'] = datetime.utcnow().isoformat() + 'Z'
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        commit_message = f"[自动更新] {now} - 更新元数据"
        
        content = json.dumps(metadata, ensure_ascii=False, indent=2)
        return self._write_file(metadata_path, content, commit_message)

    def get_metadata(self) -> Dict[str, Any]:
        """获取元数据"""
        metadata_path = f"{self.data_dir}/metadata/last_updated.json"
        
        exists, content = self._read_file(metadata_path)
        
        if not exists or not content:
            return {}
        
        try:
            return json.loads(content)
        except:
            return {}
