#!/usr/bin/env python3
"""
SAMR 国家标准爬虫 - 独立运行脚本
直接爬取 openstd.samr.gov.cn
"""
import sys
import os
import json
import logging
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('samr_monitor')

from laws_regulations_monitor.crawlers.samr_crawler import SAMRCrawler


def main():
    logger.info("=" * 60)
    logger.info("SAMR 国家标准爬虫启动")
    logger.info("=" * 60)

    config = {'base_url': 'http://openstd.samr.gov.cn/bzgk/std/'}
    crawler = SAMRCrawler(config, lookback_days=730)

    results = []
    keywords = ['数据安全', '网络安全', '个人信息', '信息安全', '人工智能', '密码', '等级保护']

    for kw in keywords:
        try:
            items = crawler._search_by_keyword(kw, max_pages=2)
            for item in items:
                item['level'] = 'L4'
                item['type'] = '国家标准'
                item['author'] = '国家市场监督管理总局'
            results.extend(items)
            logger.info(f"  [{kw}]: {len(items)} 条")
        except Exception as e:
            logger.warning(f"  [{kw}] 失败: {e}")

    # 去重
    seen = set()
    unique = []
    for r in results:
        if r['title'] not in seen:
            seen.add(r['title'])
            unique.append(r)

    logger.info(f"\n共获取 {len(unique)} 条标准（去重后）")

    # 按日期排序
    unique.sort(key=lambda x: x.get('date', ''), reverse=True)

    # 输出
    out = {
        'total': len(unique),
        'records': unique,
        'summary': {'L4': len(unique)},
    }
    out_path = os.path.dirname(__file__) + '/samr_latest.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info(f"结果写入 {out_path}")

    # 打印摘要
    for r in unique[:10]:
        logger.info(f"  [{r['date']}] {r['doc_number']} - {r['title'][:50]}")
    if len(unique) > 10:
        logger.info(f"  ... 还有 {len(unique) - 10} 条")


if __name__ == '__main__':
    main()
