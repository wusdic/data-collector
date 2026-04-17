"""
GitHub 客户端
将下载的法规文件同步到 data-collector 仓库
"""

import os
import base64
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub 文件管理客户端"""

    API_BASE = "https://api.github.com"

    def __init__(self, config: Dict[str, Any]):
        self.owner = config['owner']
        self.repo = config['repo']
        self.branch = config.get('branch', 'main')
        
        # Token 优先从环境变量读取
        self.token = (
            os.environ.get('GITHUB_TOKEN') or
            self._load_token_from_config() or
            config.get('token', '')
        )
        
        self.local_downloads_dir = config.get('local_downloads_dir', './downloads')
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'LawRegulationsMonitor/1.0'
        })

    def _load_token_from_config(self) -> Optional[str]:
        """从 ~/.github_config 读取 token"""
        config_paths = [
            os.path.expanduser('~/.github_config'),
            os.path.join(os.path.dirname(__file__), '..', '.github_config'),
            '/home/gem/workspace/agent/workspace/data-collector/.github_config',
        ]
        
        for path in config_paths:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    for line in f:
                        if line.startswith('GITHUB_TOKEN='):
                            return line.split('=', 1)[1].strip()
        return None

    def _get_file_path(self, level: str, filename: str) -> str:
        """获取 GitHub 上的文件路径"""
        # dir_structure 中定义的路径映射
        path_map = {
            'L1_国家法律': 'laws/L1_国家法律/',
            'L2_行政法规': 'laws/L2_行政法规/',
            'L3_部门文件': 'laws/L3_部门文件/',
            'L4_国家标准': 'standards/L4_国家标准/',
            'L5_行业标准': 'standards/L5_行业标准/',
            'L6_地方文件': 'laws/L6_地方文件/',
            'L7_地方标准': 'standards/L7_地方标准/',
            '执法案例库': 'cases/',
        }
        base_path = path_map.get(level, 'laws/')
        return f"{base_path}{filename}"

    def file_exists(self, path: str) -> Tuple[bool, Optional[Dict]]:
        """检查文件是否已存在于 GitHub"""
        url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/contents/{path}"
        params = {'ref': self.branch}
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return True, resp.json()
            elif resp.status_code == 404:
                return False, None
            else:
                logger.warning(f"检查文件存在性失败: {resp.status_code} - {resp.text}")
                return False, None
        except Exception as e:
            logger.error(f"GitHub API 请求失败: {e}")
            return False, None

    def upload_file(self, local_path: str, github_path: str, 
                    commit_message: str = None) -> Tuple[bool, str]:
        """
        上传文件到 GitHub
        
        Args:
            local_path: 本地文件路径
            github_path: GitHub 仓库中的目标路径
            commit_message: 提交信息
            
        Returns:
            (成功标志, 文件URL或错误信息)
        """
        if not os.path.exists(local_path):
            return False, f"本地文件不存在: {local_path}"
        
        # 读取文件内容
        with open(local_path, 'rb') as f:
            content = f.read()
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        # 检查文件是否已存在
        exists, existing = self.file_exists(github_path)
        
        # 构建请求
        url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/contents/{github_path}"
        payload = {
            'message': commit_message or f'Add {os.path.basename(local_path)}',
            'content': encoded_content,
            'branch': self.branch,
        }
        
        if exists and existing:
            # 更新已存在的文件，需要传入当前 sha
            payload['sha'] = existing['sha']
        
        try:
            resp = self.session.put(url, json=payload, timeout=30)
            data = resp.json()
            
            if resp.status_code in (200, 201):
                file_url = data.get('content', {}).get('html_url', '')
                logger.info(f"文件上传成功: {github_path}")
                return True, file_url
            else:
                error = data.get('message', f'HTTP {resp.status_code}')
                logger.error(f"上传失败 [{github_path}]: {error}")
                return False, error
        except Exception as e:
            logger.error(f"上传异常: {e}")
            return False, str(e)

    def download_and_push(self, url: str, level: str, filename: str,
                          commit_message: str = None) -> Tuple[bool, str, str]:
        """
        从 URL 下载文件并推送到 GitHub
        
        Args:
            url: 文件下载地址
            level: 层级标识 (L1_国家法律 等)
            filename: 保存的文件名
            commit_message: 提交信息
            
        Returns:
            (成功标志, github_path, github_url)
        """
        import urllib.request
        
        github_path = self._get_file_path(level, filename)
        
        # 检查是否已存在
        exists, _ = self.file_exists(github_path)
        if exists:
            logger.info(f"文件已存在，跳过: {github_path}")
            return True, github_path, f"https://github.com/{self.owner}/{self.repo}/blob/{self.branch}/{github_path}"
        
        # 下载文件
        tmp_path = os.path.join(self.local_downloads_dir, level, filename)
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        
        try:
            # 带UA的下载
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read()
            
            with open(tmp_path, 'wb') as f:
                f.write(content)
            
            logger.info(f"下载成功: {url} -> {tmp_path}")
            
        except Exception as e:
            logger.error(f"下载失败 [{url}]: {e}")
            return False, '', str(e)
        
        # 推送到 GitHub
        if commit_message is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            commit_message = f"[自动更新] {date_str} - {filename}"
        
        success, result = self.upload_file(tmp_path, github_path, commit_message)
        
        if success:
            github_url = result
            return True, github_path, github_url
        else:
            return False, '', result

    def sync_local_directory(self, level: str, commit_message: str = None) -> Dict[str, Any]:
        """
        同步本地下载目录到 GitHub
        
        Args:
            level: 层级标识
            commit_message: 提交信息
            
        Returns:
            {succeeded: [], skipped: [], failed: []}
        """
        local_dir = os.path.join(self.local_downloads_dir, level)
        
        if not os.path.exists(local_dir):
            logger.warning(f"本地目录不存在: {local_dir}")
            return {'succeeded': [], 'skipped': [], 'failed': []}
        
        results = {'succeeded': [], 'skipped': [], 'failed': []}
        
        for filename in os.listdir(local_dir):
            if filename.startswith('.'):
                continue
            
            local_path = os.path.join(local_dir, filename)
            if not os.path.isfile(local_path):
                continue
            
            github_path = self._get_file_path(level, filename)
            exists, _ = self.file_exists(github_path)
            
            if exists:
                results['skipped'].append(filename)
                continue
            
            success, result = self.upload_file(local_path, github_path, commit_message)
            
            if success:
                results['succeeded'].append({'filename': filename, 'url': result})
            else:
                results['failed'].append({'filename': filename, 'error': result})
        
        return results

    def create_or_update_index(self, level: str, records: List[Dict], 
                                 readme_template: str = None) -> bool:
        """
        为每个层级创建/更新索引 README
        
        Args:
            level: 层级标识
            records: 该层级的所有记录
            readme_template: README 模板
        """
        index_path = f"{self._get_file_path(level, '')}README.md"
        
        if readme_template is None:
            readme_content = self._default_readme_template(level, records)
        else:
            readme_content = readme_template
        
        # 直接调用 API 更新 README（不依赖本地文件）
        return self._update_readme(index_path, readme_content, 
                                  f"更新索引 - {level} ({datetime.now().strftime('%Y-%m-%d')})")

    def _default_readme_template(self, level: str, records: List[Dict]) -> str:
        """生成默认 README 内容"""
        level_names = {
            'L1_国家法律': 'L1-国家法律',
            'L2_行政法规': 'L2-行政法规',
            'L3_部门文件': 'L3-部门文件',
            'L4_国家标准': 'L4-国家标准',
            'L5_行业标准': 'L5-行业标准',
            'L6_地方文件': 'L6-地方文件',
            'L7_地方标准': 'L7-地方标准',
            '执法案例库': '执法案例库',
        }
        
        lines = [
            f"# {level_names.get(level, level)}",
            "",
            f"共 {len(records)} 条记录",
            "",
            "## 文件列表",
            "",
            "| 序号 | 文件名 | 原文链接 |",
            "| --- | --- | --- |",
        ]
        
        for i, rec in enumerate(records, 1):
            filename = rec.get('filename', rec.get('title', ''))
            url = rec.get('source_url', rec.get('url', ''))
            url_md = f"[查看]({url})" if url else "-"
            lines.append(f"| {i} | {filename} | {url_md} |")
        
        lines.append("")
        lines.append(f"> 🤖 由 LawRegulationsMonitor 自动生成 | 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        return '\n'.join(lines)

    def _update_readme(self, path: str, content: str, commit_message: str = None) -> bool:
        """直接通过 API 更新 README"""
        exists, existing = self.file_exists(path)
        
        url = f"{self.API_BASE}/repos/{self.owner}/{self.repo}/contents/{path}"
        payload = {
            'message': commit_message or f"更新索引 {datetime.now().strftime('%Y-%m-%d')}",
            'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            'branch': self.branch,
        }
        
        if exists and existing:
            payload['sha'] = existing['sha']
        
        try:
            resp = self.session.put(url, json=payload, timeout=15)
            return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"更新 README 失败: {e}")
            return False
