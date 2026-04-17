"""
适用性匹配引擎
根据企业画像，匹配适用的义务条款
"""

from typing import List, Dict, Any
from .obligation_extractor import Obligation


def match_company_obligations(
    company_profile: dict,
    obligations: List[Obligation]
) -> List[dict]:
    """
    6维匹配：判断义务条款是否适用于给定企业
    
    维度：
    1. 行业匹配：义务的适用行业 ∩ 单位行业
    2. 地域匹配：义务的适用地区 ∩ 单位所在地
    3. 规模匹配：义务的适用规模 ∩ 单位规模
    4. 数据类型匹配：义务涉及的数据类型 ∩ 单位数据类型
    5. 用户群体：若有未成年人 → 自动叠加未成年人保护法义务
    6. 跨境业务：若有跨境 → 自动叠加数据出境合规义务
    
    Args:
        company_profile: 企业画像
            - industry: str 行业
            - scale: str 规模 (大型/中型/小型)
            - province: str 省份
            - city: str 城市
            - data_types: List[str] 数据类型列表
            - user_groups: List[str] 用户群体(含"未成年人"则触发)
            - cross_border: bool 是否有跨境业务
        obligations: 义务条款列表
    
    Returns:
        匹配的义务列表(含匹配原因)
    """
    if not obligations:
        return []
    
    matched = []
    
    # 企业画像字段
    industry = company_profile.get('industry', '')
    scale = company_profile.get('scale', '')
    province = company_profile.get('province', '')
    city = company_profile.get('city', '')
    data_types = company_profile.get('data_types', [])
    user_groups = company_profile.get('user_groups', [])
    cross_border = company_profile.get('cross_border', False)
    
    for ob in obligations:
        reasons = []
        matched_dims = 0
        total_dims = 0
        
        appl = ob.applicability or {}
        
        # 1. 行业匹配
        target_industries = appl.get('industries', [])
        if target_industries:
            total_dims += 1
            # 宽松匹配：只要有一个行业匹配即算匹配
            if industry and any(ind in industry or industry in ind for ind in target_industries):
                matched_dims += 1
                reasons.append(f"行业匹配: {target_industries} ∩ {industry}")
            else:
                reasons.append(f"行业不匹配: 需要{target_industries}, 企业{industry}")
        else:
            # 无行业限定则默认匹配
            matched_dims += 1
        
        # 2. 地域匹配
        target_regions = appl.get('regions', [])
        if target_regions:
            total_dims += 1
            location = f"{province}{city}"
            if any(reg in location or location in reg for reg in target_regions):
                matched_dims += 1
                reasons.append(f"地域匹配: {target_regions} ∩ {location}")
            else:
                reasons.append(f"地域不匹配: 需要{target_regions}, 企业{location}")
        else:
            # 无地域限定则默认匹配
            matched_dims += 1
        
        # 3. 规模匹配
        target_scales = appl.get('scale', [])
        if target_scales:
            total_dims += 1
            if scale and any(sc in scale for sc in target_scales):
                matched_dims += 1
                reasons.append(f"规模匹配: {target_scales} ∩ {scale}")
            elif '所有' in target_scales or '任何' in target_scales:
                matched_dims += 1
                reasons.append("规模: 适用于所有规模")
            else:
                reasons.append(f"规模不匹配: 需要{target_scales}, 企业{scale}")
        else:
            matched_dims += 1
        
        # 4. 数据类型匹配
        target_data_types = appl.get('data_types', [])
        if target_data_types:
            total_dims += 1
            if data_types and any(dt in ' '.join(data_types) for dt in target_data_types):
                matched_dims += 1
                reasons.append(f"数据类型匹配: {target_data_types} ∩ {data_types}")
            else:
                reasons.append(f"数据类型不匹配: 需要{target_data_types}, 企业{data_types}")
        else:
            matched_dims += 1
        
        # 5. 未成年人用户群体 → 强制叠加未成年人保护义务
        if '未成年人' in user_groups:
            if ob.regulation_id and '未成年人保护' in ob.regulation_id:
                matched_dims += 1
                reasons.append("未成年人用户 → 适用未成年人保护法")
        
        # 6. 跨境业务 → 强制叠加数据出境合规义务
        if cross_border:
            if ob.regulation_id and any(kw in ob.regulation_id for kw in ['数据出境', '跨境', '个人信息出境']):
                matched_dims += 1
                reasons.append("跨境业务 → 适用数据出境合规")
        
        # 至少4维匹配(或无明确限制)则视为适用
        # 放宽条件：有行业匹配时即视为相关
        if matched_dims >= max(1, total_dims - 1) or total_dims == 0:
            matched.append({
                'obligation': ob,
                'reasons': reasons,
                'match_score': f"{matched_dims}/{total_dims}" if total_dims > 0 else "N/A",
                'applicability_level': 'high' if matched_dims == total_dims else 'medium'
            })
    
    return matched


def get_special_obligations(company_profile: dict) -> List[Obligation]:
    """
    获取因特殊属性自动叠加的义务
    如：未成年人保护、数据出境合规
    """
    special = []
    
    user_groups = company_profile.get('user_groups', [])
    cross_border = company_profile.get('cross_border', False)
    
    # 未成年人保护义务
    if '未成年人' in user_groups:
        special.append(Obligation(
            regulation_id="未成年人保护法_强制叠加",
            article_number="通用",
            obligation_type="must",
            content="处理不满十四周岁未成年人个人信息应取得其父母或监护人的同意",
            keywords=["未成年人", "同意", "监护人"],
            applicability={
                'industries': ['个人信息处理'],
                'scale': ['所有'],
                'data_types': ['个人信息'],
                'regions': []
            }
        ))
    
    # 数据出境合规义务
    if cross_border:
        special.append(Obligation(
            regulation_id="数据出境法规_强制叠加",
            article_number="通用",
            obligation_type="must",
            content="向境外提供个人信息应通过国家网信部门组织的安全评估或标准合同或认证",
            keywords=["数据出境", "安全评估", "标准合同"],
            applicability={
                'industries': ['个人信息处理', '数据处理'],
                'scale': ['大型'],
                'data_types': ['个人信息', '重要数据'],
                'regions': []
            }
        ))
    
    return special


if __name__ == "__main__":
    # 简单测试
    from engine.obligation_extractor import Obligation, extract_obligations
    
    test_text = """
    网络运营者应当按照网络安全等级保护制度的要求，履行下列安全保护义务：
    采取数据分类、重要数据备份和加密等措施。
    处理个人信息应当遵循合法、正当、必要原则。
    """
    
    obligations = extract_obligations(test_text, "测试法规")
    
    company = {
        'industry': '互联网',
        'scale': '大型',
        'province': '北京',
        'city': '北京',
        'data_types': ['个人信息', '重要数据'],
        'user_groups': ['成年人'],
        'cross_border': True
    }
    
    matched = match_company_obligations(company, obligations)
    print(f"匹配到 {len(matched)} 条义务:")
    for m in matched:
        print(f"  [{m['obligation'].obligation_type}] {m['obligation'].content[:40]}...")
        print(f"    匹配分数: {m['match_score']}")
        print(f"    原因: {m['reasons']}")