"""
网信办爬虫
https://www.cac.gov.cn/
来源: 
  - L3: 部门规章/规范性文件 (column/regulations)
  - 执法案例库 (column/case)
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional

from .base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class CACCrawler(BaseCrawler):
    """网信办官网爬虫"""

    # 执法案例类型
    CASE_TYPES = {
        '行政处罚': '行政处罚',
        '行政罚款': '行政处罚',
        '责令改正': '行政处罚',
        '司法判例': '司法判例',
        '执法解读': '执法解读',
        '监管问答': '监管问答',
    }

    def __init__(self, config: Dict[str, Any], lookback_days: int = 30):
        super().__init__(config, lookback_days)
        self.base_url = config.get('base_url', 'https://www.cac.gov.cn/')
        self.search_url = config.get('search_url', 'https://www.cac.gov.cn/search/')

    def crawl(self, **kwargs) -> List[Dict[str, Any]]:
        """
        爬取网信办数据
        - 部门规章/规范性文件 (L3)
        - 执法案例
        """
        results = []
        
        # L3: 部门文件
        regulations = self._crawl_regulations()
        for reg in regulations:
            reg['level'] = 'L3'
            reg['type'] = '部门规章'
            reg['author'] = '国家互联网信息办公室'
        results.extend(regulations)
        
        # 执法案例库
        cases = self._crawl_cases()
        for case in cases:
            case['level'] = 'case'
        results.extend(cases)
        
        return self._deduplicate(results)

    def _crawl_regulations(self) -> List[Dict[str, Any]]:
        """爬取部门规章和规范性文件"""
        results = []
        
        # 网信办法规栏目
        regulation_urls = [
            f"{self.base_url}column/regulations.html",     # 法规制度
            f"{self.base_url}column/4858/",                 # 部门规章
            f"{self.base_url}column/4859/",                 # 规范性文件
        ]
        
        for url in regulation_urls:
            try:
                content = self._make_request(url)
                if content:
                    items = self._parse_article_list(content, url, 'regulation')
                    results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"CAC 法规爬取失败 [{url}]: {e}")
        
        return results

    def _crawl_cases(self) -> List[Dict[str, Any]]:
        """爬取执法案例"""
        results = []
        
        # 网信办执法案例栏目
        case_urls = [
            f"{self.base_url}column/case.html",            # 执法案例
            f"{self.base_url}column/6590/",                 # 监管执法
        ]
        
        for url in case_urls:
            try:
                content = self._make_request(url)
                if content:
                    items = self._parse_article_list(content, url, 'case')
                    results.extend(items)
                self._rate_limit()
            except Exception as e:
                logger.warning(f"CAC 案例爬取失败 [{url}]: {e}")
        
        return results

    def _parse_article_list(self, html: str, base_url: str, 
                            item_type: str = 'regulation') -> List[Dict[str, Any]]:
        """
        解析网信办文章列表
        
        Args:
            html: HTML 内容
            base_url: 基础 URL
            item_type: regulation 或 case
        """
        results = []
        
        # 网信办列表常见结构
        # <a href="/a/2024/0105/12345.html" class="title">标题</a>
        # 或 <li><a href="...">标题</a><span>2024-01-05</span></li>
        
        patterns = [
            # 标准列表项: <a href="/a/...">标题</a> + 日期
            r'<a[^>]+href="(/a/\d{4}/\d{4}/\d+\.html)"[^>]*>([^<]+)</a>',
            # 带日期的列表项
            r'<li[^>]*>.*?<a[^>]+href="(/a/\d{4}/\d{4}/\d+\.html)"[^>]*>([^<]+)</a>.*?(\d{4}-\d{2}-\d{2})',
            # jinja 模板结构
            r'<a[^>]+href="([^"]+)"[^>]+class="[^"]*title[^"]*"[^>]*>([^<]+)</a>',
        ]
        
        seen = set()
        
        for pattern in patterns:
            matches = re.finditer(pattern, html, re.DOTALL)
            for m in matches:
                if len(m.groups()) >= 2:
                    url = m.group(1)
                    title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    date = m.group(3) if len(m.groups()) >= 3 else None
                else:
                    continue
                
                if not title:
                    continue
                
                title = self._clean_text(title)
                key = f"{url}:{title}"
                if key in seen:
                    continue
                
                # 过滤非相关内容
                exclude_keywords = ['关于', '招聘', '新闻', '通知', '公告']
                if item_type == 'regulation':
                    # 法规文件特征词
                    law_keywords = ['办法', '规定', '条例', '细则', '规范', 
                                   '制度', '决定', '意见', '通知（规范性）']
                    if not self._filter_by_keywords(title, law_keywords):
                        continue
                
                seen.add(key)
                full_url = f"{self.base_url.rstrip('/')}{url}" if url.startswith('/') else url
                
                # 检查日期是否在范围内
                if date and not self._is_recent(date):
                    continue
                
                if item_type == 'case':
                    case_type = self._infer_case_type(title)
                    results.append({
                        'title': title,
                        'url': full_url,
                        'date': date or '',
                        'case_type': case_type,
                        'summary': '',
                        'result': '',
                        'related_laws': '',
                        'authority': '国家互联网信息办公室',
                    })
                else:
                    results.append({
                        'title': title,
                        'url': full_url,
                        'date': date or '',
                        'author': '国家互联网信息办公室',
                        'doc_number': self._extract_doc_number(title),
                        'summary': '',
                        'download_url': '',
                        'status': '现行有效',
                    })
        
        return results

    def _clean_text(self, text: str) -> str:
        """清理 HTML 文本"""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _infer_case_type(self, title: str) -> str:
        """从标题推断案例类型"""
        if '处罚' in title or '罚款' in title or '通报' in title:
            return '行政处罚'
        elif '判例' in title or '判决' in title or '裁定' in title:
            return '司法判例'
        elif '解读' in title or '解析' in title:
            return '执法解读'
        elif '问答' in title or '问答' in title:
            return '监管问答'
        return '行政处罚'  # 默认

    def get_case_detail(self, case_url: str) -> Optional[Dict[str, Any]]:
        """
        获取案例详细信息
        
        Args:
            case_url: 案例页面 URL
        """
        if not case_url.startswith('http'):
            case_url = f"{self.base_url.rstrip('/')}/{case_url.lstrip('/')}"
        
        content = self._make_request(case_url)
        if not content:
            return None
        
        detail = {
            'url': case_url,
            'title': '',
            'case_type': '行政处罚',
            'authority': '国家互联网信息办公室',
            'case_date': '',
            'summary': '',
            'key_points': '',
            'result': '',
            'related_laws': '',
        }
        
        # 提取标题
        title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', content)
        if title_m:
            detail['title'] = self._clean_text(title_m.group(1))
        
        # 提取日期
        date_m = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)', content)
        if date_m:
            detail['case_date'] = date_m.group(1)
        
        # 提取正文内容（用于摘要和要点）
        content_m = re.search(r'<div[^>]+class="[^"]*content[^"]*"[^>]*>(.*?)</div>', 
                              content, re.DOTALL)
        if content_m:
            text = self._clean_text(content_m.group(1))
            detail['summary'] = text[:500] if text else ''
            
            # 提取认定要点
            if '认定' in text:
                key_m = re.search(r'认定[：:]([^。]+)', text)
                if key_m:
                    detail['key_points'] = key_m.group(1)
            
            # 提取处罚结果
            if '处罚' in text or '罚款' in text:
                result_m = re.search(r'((?:罚款|处罚|责令|警告)[^。]+)', text)
                if result_m:
                    detail['result'] = result_m.group(1)
            
            # 提取涉及法规
            laws = re.findall(r'《([^》]+)》', text)
            if laws:
                detail['related_laws'] = '、'.join(laws[:5])
        
        return detail

    def search_by_keyword(self, keyword: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """
        关键词搜索
        
        Args:
            keyword: 搜索关键词
            max_results: 最大结果数
        """
        results = []
        
        # 构造搜索 URL
        search_url = f"{self.search_url}?q={keyword}"
        
        try:
            content = self._make_request(search_url)
            if content:
                results = self._parse_article_list(content, search_url, 'regulation')
        except Exception as e:
            logger.warning(f"CAC 搜索失败 [{keyword}]: {e}")
        
        return results[:max_results]
