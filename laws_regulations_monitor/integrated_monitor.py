#!/usr/bin/env python3
"""
[废弃] 此文件已由 scheduler/job_scheduler.py + engine/crawler_engine.py 替代
请使用: python -m scheduler.job_scheduler 或 python -m engine.crawler_engine
"""
法规监控整合脚本 - 最终版
使用可及来源抓取法规，对接飞书多维表格

来源覆盖情况：
  ✅ CAC 网信办 - JSON API (100条全量)
  ⚠️  SAMR 标准委 - 可测试
  ❌ FLK 全国人大 - SPA 无法访问
  ❌ 其他 L1/L2 来源 - 网络不通
"""
import sys
import os
import json
import logging
import time
import re
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('integrated_monitor')

import requests

# ═══════════════════════════════════════════════════════════════
# 1. CAC 爬虫（已修复）
# ═══════════════════════════════════════════════════════════════
class CACCrawler:
    """网信办爬虫 - 使用官方 JSON API，完整历史数据"""

    CHANNEL_CODES = {
        'A09370301': ('法律', 'L1'),
        'A09370302': ('行政法规', 'L2'),
        'A09370303': ('部门规章', 'L3'),
        'A09370304': ('司法解释', 'L4'),
        'A09370305': ('规范性文件', 'L3'),
        'A09370306': ('政策文件', 'L3'),
    }

    def __init__(self):
        self.base_url = 'https://www.cac.gov.cn'
        self.api_url = f'{self.base_url}/cms/JsonList'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LawMonitor/1.0)',
            'Referer': self.base_url,
        })

    def crawl(self, lookback_days=365) -> List[Dict]:
        results = []
        for code, (name, level) in self.CHANNEL_CODES.items():
            logger.info(f"  → CAC [{name}]...")
            try:
                items = self._crawl_channel(code, level, lookback_days)
                logger.info(f"    {len(items)} 条")
                results.extend(items)
            except Exception as e:
                logger.warning(f"    失败: {e}")
        return results

    def _crawl_channel(self, channel_code, level, lookback_days, max_pages=50) -> List[Dict]:
        results = []
        page = 1
        cutoff_ts = (datetime.now().timestamp() - lookback_days * 86400) * 1000

        while page <= max_pages:
            try:
                items = self._fetch_page(channel_code, page)
                if not items:
                    break

                for item in items:
                    pubtime = item.get('pubtime', '')
                    if isinstance(pubtime, str) and pubtime:
                        try:
                            ts = datetime.strptime(pubtime.split('.')[0], '%Y-%m-%d %H:%M:%S').timestamp()
                            if ts * 1000 < cutoff_ts:
                                return results
                        except:
                            pass

                    title = item.get('topic', '').strip()
                    infourl = item.get('infourl', '')
                    if not title or not infourl:
                        continue

                    if infourl.startswith('//'):
                        url = f'https:{infourl}'
                    elif infourl.startswith('/'):
                        url = f'{self.base_url}{infourl}'
                    else:
                        url = infourl

                    status = '现行有效'
                    if any(k in title for k in ['征求意见', '（征求意见稿）', '(征求意见稿)', '草案']):
                        status = '征求意见稿'

                    author = '国家互联网信息办公室'
                    if level == 'L1':
                        author = '全国人大常委会'
                    elif level == 'L2':
                        author = '国务院'

                    results.append({
                        'title': title,
                        'url': url,
                        'date': pubtime.split(' ')[0] if pubtime else '',
                        'level': level,
                        'type': self._infer_type(title, level),
                        'author': author,
                        'status': status,
                        'source': 'CAC',
                    })

                page += 1
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"  page {page} 失败: {e}")
                break
        return results

    def _fetch_page(self, channel_code, page_num) -> List:
        params = {
            'channelCode': channel_code,
            'perPage': '20',
            'pageno': str(page_num),
            'condition': '0',
            'fuhao': '=',
            'value': '',
        }
        r = self.session.get(self.api_url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get('list', [])

    def _infer_type(self, title, level):
        if level == 'L1': return '法律'
        if level == 'L2': return '行政法规'
        kw_map = {
            '办法': '部门规章', '规定': '部门规章', '条例': '行政法规',
            '细则': '部门规章', '规范': '规范性文件', '制度': '规范性文件',
            '决定': '部门规章', '意见': '规范性文件', '通知': '规范性文件',
            '指南': '规范性文件', '清单': '规范性文件',
        }
        for kw, t in kw_map.items():
            if kw in title:
                return t
        return '部门规章'


# ═══════════════════════════════════════════════════════════════
# 2. 字段映射
# ═══════════════════════════════════════════════════════════════
def field_mapping(record: Dict) -> Dict:
    title = record.get('title', '')
    level = record.get('level', 'L3')
    reg_type = record.get('type', '部门规章')
    author = record.get('author', '')
    date_str = record.get('date', '')
    status = record.get('status', '现行有效')
    url = record.get('url', '')

    date_ts = 0
    if date_str:
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            date_ts = int(dt.timestamp() * 1000)
        except:
            pass

    level_map = {
        'L1': 'L1-国家法律',
        'L2': 'L2-行政法规',
        'L3': 'L3-部门/政府规章',
        'L4': 'L4-国家标准',
        'L5': 'L5-行业标准',
    }
    level_display = level_map.get(level, level)

    return {
        '法规标题': [{'text': title, 'type': 'text'}],
        '法规类型': reg_type,
        '来源层级': level_display,
        '发文机关': [{'text': author, 'type': 'text'}] if author else [],
        '发布日期': date_ts if date_ts else 0,
        '状态': status,
        '原文链接': [{'link': url, 'text': '查看原文'}] if url else [],
        '标签': _infer_tags(title),
    }


def _infer_tags(title: str) -> List[str]:
    tags = []
    kw_tags = {
        '数据安全': '数据安全', '网络安全': '网络安全', '个人信息': '个人信息',
        '人脸识别': '人脸识别', '算法': '算法推荐', '生成式AI': '生成式AI',
        '人工智能': '人工智能安全', '深度合成': '深度合成',
        '出境': '数据出境', '跨境': '数据跨境',
        '关键信息基础设施': '关键信息基础设施',
        '等级保护': '等级保护', '密码': '密码',
        '儿童': '儿童个人信息', '未成年': '未成年人网络保护',
        'App': 'App合规', '汽车': '汽车数据',
        '健康医疗': '健康医疗', '金融': '金融数据',
        '工业': '工业数据', '电信': '电信行业',
        '教育': '教育数据', '交通': '交通数据',
        '电商': '网络交易', '自动化决策': '自动化决策',
        '网络暴力': '网络暴力治理', '直播': '直播电商',
        '虚拟人': '数字虚拟人', '拟人化': '人机交互',
    }
    for kw, tag in kw_tags.items():
        if kw in title:
            if tag not in tags:
                tags.append(tag)
    return tags


# ═══════════════════════════════════════════════════════════════
# 3. 主程序
# ═══════════════════════════════════════════════════════════════
def main():
    logger.info("=" * 60)
    logger.info("法规监控整合系统启动")
    logger.info("=" * 60)

    # Step 1: 抓取 CAC
    logger.info("[1/3] 抓取 CAC 网信办法规...")
    cac = CACCrawler()
    cac_records = cac.crawl(lookback_days=730)  # 2年回查
    logger.info(f"    共获取 {len(cac_records)} 条记录")

    # Step 2: 打印摘要（供人工核对）
    logger.info("[2/3] 数据摘要：")
    by_level = {}
    for r in cac_records:
        lv = r['level']
        by_level[lv] = by_level.get(lv, 0) + 1
    for lv in sorted(by_level.keys()):
        logger.info(f"    {lv}: {by_level[lv]} 条")

    # Step 3: 输出 JSON 供外部调用
    output = {
        'total': len(cac_records),
        'records': [field_mapping(r) for r in cac_records],
        'summary': by_level,
        'new_count': 0,  # 由调用方填入
    }

    output_path = os.path.join(os.path.dirname(__file__), 'cac_latest.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"[3/3] 结果已写入 {output_path}")
    logger.info(f"    可通过飞书工具创建 {len(output['records'])} 条记录")
    logger.info("=" * 60)

    return output


if __name__ == '__main__':
    main()
