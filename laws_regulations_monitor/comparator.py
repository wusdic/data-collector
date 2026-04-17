"""
增量比对引擎
对比新爬取的法规与现有库，找出新增和变更项
"""

import logging
import os
from typing import Dict, List, Any, Tuple, Set, Optional
from datetime import datetime
import hashlib
import yaml

logger = logging.getLogger(__name__)


class Comparator:
    """增量比对引擎"""

    def __init__(self, bitable_client, github_client=None, github_data_store=None):
        self.bitable = bitable_client
        self.github = github_client
        self.github_store = github_data_store
        
        # 标题去重集合（从飞书表格或 GitHub JSON 加载）
        self._existing_titles: Dict[str, Set[str]] = {}
        # URL 去重集合
        self._existing_urls: Dict[str, Set[str]] = {}
        # 文号去重集合
        self._existing_doc_numbers: Dict[str, Set[str]] = {}
        
        # 加载配置获取 table_id
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """从 config.yaml 加载配置"""
        config_path = os.path.join(
            os.path.dirname(__file__), 'config.yaml'
        )
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        return {}

    def load_existing(self, use_github: bool = False) -> None:
        """
        从飞书表格或 GitHub JSON 加载现有记录，建立去重索引
        
        Args:
            use_github: 是否使用 GitHub JSON 数据源
        """
        if use_github and self.github_store:
            self._load_from_github()
        else:
            self._load_from_bitable()
        
        logger.info("现有记录索引建立完成")

    def _load_from_bitable(self) -> None:
        """从飞书表格加载现有记录"""
        self.bitable.load_all_records()
        
        stats = self.bitable.get_table_stats()
        logger.info(f"已加载现有记录: {stats}")
        
        # 建立各表的索引
        for table_name, table_info in self.bitable.tables.items():
            table_id = table_info['table_id']
            
            if table_id in self.bitable._all_records:
                titles = set()
                urls = set()
                doc_numbers = set()
                
                for rec in self.bitable._all_records[table_id]:
                    # 标题
                    title = self.bitable._extract_title(rec)
                    if title:
                        titles.add(self._normalize_title(title))
                    
                    # URL
                    if table_name == '法规主表':
                        url_field = self.bitable._extract_field(rec, '原文链接')
                        if url_field:
                            if isinstance(url_field, dict):
                                urls.add(url_field.get('link', ''))
                            elif isinstance(url_field, str):
                                urls.add(url_field)
                    
                    # 文号
                    doc_num = self.bitable._extract_field(rec, '文号')
                    if doc_num:
                        doc_numbers.add(doc_num)
                
                self._existing_titles[table_id] = titles
                self._existing_urls[table_id] = urls
                self._existing_doc_numbers[table_id] = doc_numbers

    def _load_from_github(self) -> None:
        """从 GitHub JSON 文件加载现有记录"""
        levels = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'case']
        
        for level in levels:
            # 使用同一个 table_id（法规主表是合表）
            table_id = self._get_table_id(level)
            
            records = self.github_store.get_all_records(level)
            
            titles = set()
            urls = set()
            doc_numbers = set()
            
            for rec in records:
                title = rec.get('title', '')
                if title:
                    titles.add(self._normalize_title(title))
                
                url = rec.get('url', '')
                if url:
                    urls.add(url)
                
                doc_number = rec.get('doc_number', '')
                if doc_number:
                    doc_numbers.add(doc_number)
            
            self._existing_titles[table_id] = titles
            self._existing_urls[table_id] = urls
            self._existing_doc_numbers[table_id] = doc_numbers
            
            logger.info(f"[{level}] 从 GitHub 加载 {len(records)} 条记录")

    def _normalize_title(self, title: str) -> str:
        """标准化标题（用于比对）"""
        import re
        # 去除括号内的公告号等
        title = re.sub(r'[\[【\(（].*?[\]】\)）]', '', title)
        # 去除首尾空格
        title = title.strip()
        # 统一全角括号
        title = title.replace('（', '(').replace('）', ')')
        return title.lower()

    def find_new_records(self, new_items: List[Dict[str, Any]], 
                         level: str) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        找出全新的记录
        
        Args:
            new_items: 新爬取的条目
            level: 层级标识 (L1-L7, case)
            
        Returns:
            (new_items, updated_items, skipped_items)
        """
        new_records = []
        updated_records = []
        skipped = []
        
        table_id = self._get_table_id(level)
        if not table_id:
            logger.warning(f"未知层级: {level}")
            return [], [], new_items
        
        existing_titles = self._existing_titles.get(table_id, set())
        existing_urls = self._existing_urls.get(table_id, set())
        existing_doc_numbers = self._existing_doc_numbers.get(table_id, set())
        
        for item in new_items:
            title = item.get('title', '')
            url = item.get('url', '')
            doc_number = item.get('doc_number', '')
            
            if not title:
                skipped.append({**item, 'reason': '无标题'})
                continue
            
            norm_title = self._normalize_title(title)
            
            # 判断是否新增
            is_new = True
            reason = ''
            
            # 检查标题
            if norm_title in existing_titles:
                is_new = False
                reason = '标题已存在'
            
            # 检查 URL
            if url and url in existing_urls:
                is_new = False
                reason = 'URL已存在'
            
            # 检查文号
            if doc_number and doc_number in existing_doc_numbers:
                is_new = False
                reason = '文号已存在'
            
            if is_new:
                new_records.append(item)
            else:
                skipped.append({**item, 'reason': reason})
        
        logger.info(f"[{level}] 比对结果: 新增 {len(new_records)}, 跳过 {len(skipped)}")
        return new_records, updated_records, skipped

    def _get_table_id(self, level: str) -> str:
        """根据层级获取表格 ID（从配置读取）"""
        # 法规主表都走同一个 table_id（合表）
        if level.startswith('L'):
            # 从 config.yaml 读取
            bitable_config = self._config.get('BITABLE', {})
            tables = bitable_config.get('tables', {})
            main_table = tables.get('法规主表', {})
            return main_table.get('table_id', 'tblUkUwxCDBWKDdK')
        elif level == 'case':
            bitable_config = self._config.get('BITABLE', {})
            tables = bitable_config.get('tables', {})
            case_table = tables.get('执法案例库', {})
            return case_table.get('table_id', 'tbljSjhjzu1LtQwX')
        
        return ''

    def merge_and_save(self, new_items: List[Dict[str, Any]], level: str,
                       download_files: bool = True) -> Dict[str, Any]:
        """
        合并新记录并保存到飞书 + GitHub + GitHub JSON
        
        Args:
            new_items: 新增的记录
            level: 层级
            download_files: 是否下载文件
            
        Returns:
            {bitable: {created, updated, errors}, github: {uploaded, skipped, failed}, 
             github_json: {appended, skipped, errors}}
        """
        results = {
            'bitable': {'created': [], 'updated': [], 'errors': []},
            'github': {'uploaded': [], 'skipped': [], 'failed': []},
            'github_json': {'appended': 0, 'skipped': 0, 'errors': []},
        }
        
        if not new_items:
            logger.info(f"[{level}] 没有新记录需要处理")
            return results
        
        table_id = self._get_table_id(level)
        
        # 处理每条新记录
        for item in new_items:
            title = item.get('title', '')
            
            try:
                # 1. 构建飞书记录
                if level == 'case':
                    fields = self.bitable.build_case_fields(item)
                else:
                    fields = self.bitable.build_record_fields(level, item)
                
                # 2. 下载文件并上传到 GitHub（如需要）
                github_path = ''
                github_url = ''
                
                if download_files and self.github and item.get('download_url'):
                    url = item.get('download_url', '')
                    if url:
                        filename = self._generate_filename(item)
                        ok, path, result_url = self.github.download_and_push(
                            url=url,
                            level=level,
                            filename=filename,
                            commit_message=f"[自动] 新增 {title}"
                        )
                        if ok:
                            github_path = path
                            github_url = result_url
                            fields['全文存储路径'] = path
                            results['github']['uploaded'].append(title)
                        else:
                            results['github']['failed'].append({'title': title, 'error': result_url})
                
                # 3. 保存到飞书
                success, record_id = self.bitable.upsert_record(table_id, fields)
                
                if success:
                    results['bitable']['created'].append(title)
                    
                    # 更新本地缓存
                    if table_id not in self.bitable._cache:
                        self.bitable._cache[table_id] = {}
                    self.bitable._cache[table_id][title] = {'record_id': record_id}
                    
                    logger.info(f"✓ [{level}] 新增: {title}")
                else:
                    results['bitable']['errors'].append({'title': title, 'error': record_id})
                    logger.warning(f"✗ [{level}] 写入失败 [{title}]: {record_id}")
            
            except Exception as e:
                results['bitable']['errors'].append({'title': title, 'error': str(e)})
                logger.error(f"处理记录异常 [{title}]: {e}")
        
        # 4. 追加记录到 GitHub JSON 数据文件
        if self.github_store and new_items:
            json_result = self.github_store.append_records(level, new_items)
            results['github_json'] = {
                'appended': json_result.get('appended_count', 0),
                'skipped': json_result.get('skipped_count', 0),
                'errors': json_result.get('errors', [])
            }
            
            # 更新 metadata
            if json_result.get('appended_count', 0) > 0:
                self.github_store.update_metadata(level, json_result)
        
        return results

    def _generate_filename(self, item: Dict[str, Any]) -> str:
        """生成文件名"""
        title = item.get('title', '未命名')
        doc_number = item.get('doc_number', '')
        
        # 清理非法字符
        import re
        title = re.sub(r'[<>:"/\\|?*]', '_', title)
        
        if doc_number:
            # 优先用文号命名
            doc_number = re.sub(r'[<>:"/\\|?*]', '_', doc_number)
            return f"{doc_number}_{title[:30]}.pdf"
        else:
            return f"{title[:50]}.pdf"

    def generate_report(self, all_results: Dict[str, Dict]) -> str:
        """生成变更报告"""
        lines = [
            f"# 法律法规监控报告",
            f"",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
        ]
        
        total_new = 0
        total_errors = 0
        
        for level, result in all_results.items():
            bitable_res = result.get('bitable', {})
            github_res = result.get('github', {})
            json_res = result.get('github_json', {})
            
            created = len(bitable_res.get('created', []))
            errors = len(bitable_res.get('errors', []))
            github_ok = len(github_res.get('uploaded', []))
            json_appended = json_res.get('appended', 0)
            
            total_new += created
            total_errors += errors
            
            lines.append(f"## {level}")
            lines.append(f"- 新增记录: {created}")
            lines.append(f"- 写入失败: {errors}")
            lines.append(f"- 文件上传: {github_ok}")
            if json_appended > 0:
                lines.append(f"- JSON追加: {json_appended}")
            
            if bitable_res.get('created'):
                lines.append(f"")
                lines.append(f"新增法规:")
                for t in bitable_res['created'][:10]:
                    lines.append(f"  - {t}")
                if len(bitable_res['created']) > 10:
                    lines.append(f"  ... 还有 {len(bitable_res['created']) - 10} 条")
            
            if bitable_res.get('errors'):
                lines.append(f"")
                lines.append(f"失败记录:")
                for err in bitable_res['errors'][:5]:
                    lines.append(f"  - {err.get('title', '?')}: {err.get('error', '?')}")
            
            lines.append("")
        
        lines.append(f"## 汇总")
        lines.append(f"- 总新增: {total_new}")
        lines.append(f"- 总失败: {total_errors}")
        
        return '\n'.join(lines)
