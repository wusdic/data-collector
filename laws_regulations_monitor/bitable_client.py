"""
飞书多维表格客户端
对接 法规主表 (L1-L7) 和 执法案例库
使用 requests 直接调用飞书 Open API
"""

import logging
import base64
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import os
import requests

logger = logging.getLogger(__name__)


class BitableClient:
    """飞书多维表格读写客户端"""

    # 层级 → 单选选项名映射
    LEVEL_OPTIONS = {
        'L1': 'L1-国家法律',
        'L2': 'L2-行政法规',
        'L3': 'L3-部门/政府规章',
        'L4': 'L4-国家标准',
        'L5': 'L5-行业标准',
        'L6': 'L6-地方文件',
        'L7': 'L7-地方标准',
    }

    # 法规类型选项映射
    TYPE_OPTIONS = {
        '法律': '法律',
        '行政法规': '行政法规',
        '部门规章': '部门规章',
        '地方政府规章': '地方政府规章',
        '规范性文件': '规范性文件',
        '国家标准': '国家标准',
        '行业标准': '行业标准',
        '地方性法规': '地方性法规',
    }

    # 状态选项
    STATUS_OPTIONS = ['现行有效', '已废止', '修订中', '征求意见稿']

    API_BASE = "https://open.feishu.cn/open-apis/bitable/v1"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app_token = config['app_token']
        self.tables = config['tables']
        
        # 获取 access_token
        self.access_token = self._get_access_token()
        
        # 预加载所有现有记录（用于比对）
        self._cache: Dict[str, Dict[str, Any]] = {}  # table_id -> {title: record}
        self._all_records: Dict[str, List[Dict]] = {}

    def _get_access_token(self) -> str:
        """获取飞书 access_token"""
        # 优先从环境变量读取
        token = os.environ.get('FEISHU_ACCESS_TOKEN', '')
        if token:
            return token
        
        # 从配置文件读取
        token = self.config.get('access_token', '')
        if token:
            return token
        
        # 尝试从飞书应用凭证获取（需要 app_id 和 app_secret）
        app_id = os.environ.get('FEISHU_APP_ID', '')
        app_secret = os.environ.get('FEISHU_APP_SECRET', '')
        
        if app_id and app_secret:
            try:
                url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
                resp = requests.post(url, json={
                    "app_id": app_id,
                    "app_secret": app_secret
                }, timeout=10)
                data = resp.json()
                if data.get('code') == 0:
                    return data.get('tenant_access_token', '')
            except Exception as e:
                logger.error(f"获取 access_token 失败: {e}")
        
        logger.warning("未配置飞书 access_token，飞书写入功能可能不可用")
        return ''

    def _headers(self) -> Dict[str, str]:
        """构建请求头"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

    def load_all_records(self) -> None:
        """预加载所有表格的现有记录"""
        for table_name, table_info in self.tables.items():
            table_id = table_info['table_id']
            records = self._fetch_records(table_id)
            self._all_records[table_id] = records
            
            # 建立标题索引
            self._cache[table_id] = {}
            for rec in records:
                title = self._extract_title(rec)
                if title:
                    self._cache[table_id][title] = rec
            
            logger.info(f"已加载 {table_name} ({table_id}): {len(records)} 条记录")

    def _fetch_records(self, table_id: str, page_size: int = 500) -> List[Dict]:
        """获取表格所有记录（分页）"""
        if not self.access_token:
            logger.warning("无 access_token，无法获取记录")
            return []
        
        records = []
        page_token = None
        
        while True:
            url = f"{self.API_BASE}/apps/{self.app_token}/tables/{table_id}/records"
            params = {'page_size': page_size}
            if page_token:
                params['page_token'] = page_token
            
            try:
                resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
                data = resp.json()
                
                if data.get('code') != 0:
                    logger.error(f"获取记录失败: {data.get('msg', 'Unknown error')}")
                    break
                
                items = data.get('data', {}).get('items', [])
                records.extend(items)
                
                # 检查是否还有下一页
                has_more = data.get('data', {}).get('has_more', False)
                if not has_more:
                    break
                
                page_token = data.get('data', {}).get('page_token')
                if not page_token:
                    break
                    
            except Exception as e:
                logger.error(f"请求记录失败: {e}")
                break
        
        return records

    def _extract_title(self, record: Dict) -> str:
        """从记录中提取标题"""
        fields = record.get('fields', {})
        # 法规主表: 法规标题
        if '法规标题' in fields:
            title_field = fields['法规标题']
            if isinstance(title_field, list) and len(title_field) > 0:
                return title_field[0].get('text', '')
            elif isinstance(title_field, str):
                return title_field
        # 执法案例表: 案例标题
        if '案例标题' in fields:
            title_field = fields['案例标题']
            if isinstance(title_field, list) and len(title_field) > 0:
                return title_field[0].get('text', '')
            elif isinstance(title_field, str):
                return title_field
        return ''

    def _extract_field(self, record: Dict, field_name: str) -> Any:
        """从记录中提取字段值"""
        fields = record.get('fields', {})
        return fields.get(field_name)

    def check_exists(self, table_id: str, title: str) -> Optional[str]:
        """
        检查记录是否已存在
        
        Returns:
            record_id 如果存在，否则 None
        """
        if table_id in self._cache:
            if title in self._cache[table_id]:
                return self._cache[table_id][title].get('record_id')
        return None

    def get_record_by_title(self, table_id: str, title: str) -> Optional[Dict]:
        """根据标题查找记录"""
        if table_id in self._cache:
            return self._cache[table_id].get(title)
        return None

    def upsert_record(self, table_id: str, record_data: Dict[str, Any], 
                      record_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        插入或更新记录
        
        Args:
            table_id: 表格 ID
            record_data: 字段数据
            record_id: 若提供则为更新，否则为新建
            
        Returns:
            (成功标志, 记录ID或错误信息)
        """
        try:
            if record_id:
                # 更新现有记录
                result = self._update_record(table_id, record_id, record_data)
            else:
                # 新建记录
                result = self._create_record(table_id, record_data)
            
            if result.get('code') == 0:
                rid = result.get('data', {}).get('record', {}).get('record_id') or record_id
                return True, rid
            else:
                error = result.get('msg', str(result))
                return False, error
        except Exception as e:
            logger.error(f"upsert 记录失败: {e}")
            return False, str(e)

    def _create_record(self, table_id: str, record_data: Dict) -> Dict:
        """创建单条记录"""
        url = f"{self.API_BASE}/apps/{self.app_token}/tables/{table_id}/records"
        payload = {'fields': record_data}
        
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"创建记录失败: {e}")
            return {'code': -1, 'msg': str(e)}

    def _update_record(self, table_id: str, record_id: str, record_data: Dict) -> Dict:
        """更新记录"""
        url = f"{self.API_BASE}/apps/{self.app_token}/tables/{table_id}/records/{record_id}"
        payload = {'fields': record_data}
        
        try:
            resp = requests.put(url, headers=self._headers(), json=payload, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"更新记录失败: {e}")
            return {'code': -1, 'msg': str(e)}

    def batch_upsert(self, table_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量插入/更新记录
        
        Args:
            table_id: 表格 ID
            records: 记录列表，每条包含 title 和 fields
            
        Returns:
            {created: [], updated: [], errors: []}
        """
        results = {'created': [], 'updated': [], 'errors': []}
        
        for rec in records:
            title = rec.get('title', '')
            fields = rec.get('fields', {})
            
            existing_id = self.check_exists(table_id, title)
            
            if existing_id:
                fields['_record_id'] = existing_id
            
            success, result = self.upsert_record(table_id, fields, existing_id)
            
            if success:
                if existing_id:
                    results['updated'].append(title)
                else:
                    results['created'].append(title)
                
                # 更新缓存
                if table_id not in self._cache:
                    self._cache[table_id] = {}
                self._cache[table_id][title] = {'record_id': result}
            else:
                results['errors'].append({'title': title, 'error': result})
                logger.warning(f"记录操作失败 [{title}]: {result}")
        
        return results

    def get_table_stats(self) -> Dict[str, int]:
        """获取各表记录数统计"""
        stats = {}
        for table_name, table_info in self.tables.items():
            table_id = table_info['table_id']
            if table_id in self._all_records:
                stats[table_name] = len(self._all_records[table_id])
            else:
                stats[table_name] = 0
        return stats

    def build_record_fields(self, level: str, law_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据层级和数据构建飞书记录字段
        
        Args:
            level: L1-L7 或 case
            law_data: 包含 title, type, author, doc_number, publish_date, 
                     effective_date, status, source_url, local_path, tags
        """
        fields = {}
        
        # 标题
        fields['法规标题'] = law_data.get('title', '')
        
        # 法规类型
        law_type = law_data.get('type', '')
        if law_type in self.TYPE_OPTIONS:
            fields['法规类型'] = self.TYPE_OPTIONS[law_type]
        
        # 来源层级
        if level in self.LEVEL_OPTIONS:
            fields['来源层级'] = self.LEVEL_OPTIONS[level]
        
        # 发文机关
        author = law_data.get('author', '')
        if author:
            fields['发文机关'] = [{'text': author, 'type': 'text'}] if isinstance(author, str) else author
        
        # 文号
        if law_data.get('doc_number'):
            fields['文号'] = law_data['doc_number']
        
        # 发布日期 (需要转为毫秒时间戳)
        publish_date = law_data.get('publish_date')
        if publish_date:
            if isinstance(publish_date, str):
                # 尝试解析日期
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']:
                    try:
                        dt = datetime.strptime(publish_date, fmt)
                        fields['发布日期'] = int(dt.timestamp() * 1000)
                        break
                    except ValueError:
                        continue
            elif isinstance(publish_date, (int, float)):
                fields['发布日期'] = int(publish_date)
        
        # 生效日期
        effective_date = law_data.get('effective_date')
        if effective_date:
            if isinstance(effective_date, str):
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']:
                    try:
                        dt = datetime.strptime(effective_date, fmt)
                        fields['生效日期'] = int(dt.timestamp() * 1000)
                        break
                    except ValueError:
                        continue
            elif isinstance(effective_date, (int, float)):
                fields['生效日期'] = int(effective_date)
        
        # 状态
        status = law_data.get('status', '现行有效')
        if status in self.STATUS_OPTIONS:
            fields['状态'] = status
        
        # 原文链接
        source_url = law_data.get('source_url', '')
        if source_url:
            fields['原文链接'] = {
                'link': source_url,
                'text': source_url
            }
        
        # 全文存储路径
        if law_data.get('local_path'):
            fields['全文存储路径'] = law_data['local_path']
        
        # 标签
        tags = law_data.get('tags', [])
        if tags:
            fields['标签'] = tags
        
        return fields

    def build_case_fields(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建执法案例库记录字段"""
        fields = {}
        
        # 案例标题
        fields['案例标题'] = case_data.get('title', '')
        
        # 案例类型
        case_type = case_data.get('case_type', '')
        if case_type:
            fields['案例类型'] = case_type
        
        # 处罚/审理机关
        if case_data.get('authority'):
            fields['处罚/审理机关'] = case_data['authority']
        
        # 案例日期
        case_date = case_data.get('case_date')
        if case_date:
            if isinstance(case_date, str):
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y年%m月%d日']:
                    try:
                        dt = datetime.strptime(case_date, fmt)
                        fields['案例日期'] = int(dt.timestamp() * 1000)
                        break
                    except ValueError:
                        continue
            elif isinstance(case_date, (int, float)):
                fields['案例日期'] = int(case_date)
        
        # 涉及法规
        if case_data.get('related_laws'):
            fields['涉及法规'] = case_data['related_laws']
        
        # 案情摘要
        if case_data.get('summary'):
            fields['案情摘要'] = case_data['summary']
        
        # 认定要点
        if case_data.get('key_points'):
            fields['认定要点'] = case_data['key_points']
        
        # 处罚结果
        if case_data.get('result'):
            fields['处罚结果'] = case_data['result']
        
        # 原文链接
        source_url = case_data.get('source_url', '')
        if source_url:
            fields['原文链接'] = {
                'link': source_url,
                'text': source_url
            }
        
        return fields
