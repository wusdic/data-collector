"""
飞书集成模块
提供与飞书平台的对接功能
"""

from typing import List, Dict, Any, Optional

import logging

logger = logging.getLogger(__name__)


def feishu_search_doc_wiki(
    query: str,
    page_size: int = 20,
    doc_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    搜索飞书文档和知识库
    
    Args:
        query: 搜索关键词
        page_size: 返回数量
        doc_types: 文档类型过滤
        
    Returns:
        搜索结果列表
    """
    try:
        # 尝试使用 OpenClaw 的飞书集成
        from data_collector.integrations.feishu.client import FeishuClient
        
        client = FeishuClient()
        return client.search_doc_wiki(query, page_size, doc_types)
    except ImportError:
        logger.warning("飞书客户端未配置")
        return []
    except Exception as e:
        logger.error(f"飞书搜索失败: {e}")
        return []


def feishu_create_bitable(
    name: str,
    fields: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    创建飞书多维表格
    
    Args:
        name: 表格名称
        fields: 字段定义
        
    Returns:
        创建结果
    """
    try:
        from data_collector.integrations.feishu.client import FeishuClient
        
        client = FeishuClient()
        return client.create_bitable(name, fields)
    except ImportError:
        logger.warning("飞书客户端未配置")
        return None
    except Exception as e:
        logger.error(f"创建多维表格失败: {e}")
        return None


def feishu_send_message(
    content: str,
    receive_id: str,
    receive_id_type: str = 'open_id',
    msg_type: str = 'text'
) -> bool:
    """
    发送飞书消息
    
    Args:
        content: 消息内容
        receive_id: 接收者 ID
        receive_id_type: ID 类型 (open_id/chat_id)
        msg_type: 消息类型
        
    Returns:
        是否发送成功
    """
    try:
        from data_collector.integrations.feishu.client import FeishuClient
        
        client = FeishuClient()
        return client.send_message(content, receive_id, receive_id_type, msg_type)
    except ImportError:
        logger.warning("飞书客户端未配置")
        return False
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return False


def feishu_create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: Optional[List[str]] = None,
    description: str = ''
) -> Optional[str]:
    """
    创建飞书日历事件
    
    Args:
        summary: 日程标题
        start_time: 开始时间 (ISO 8601)
        end_time: 结束时间 (ISO 8601)
        attendees: 参会人 open_id 列表
        description: 日程描述
        
    Returns:
        事件 ID
    """
    try:
        from data_collector.integrations.feishu.client import FeishuClient
        
        client = FeishuClient()
        return client.create_calendar_event(
            summary, start_time, end_time, attendees, description
        )
    except ImportError:
        logger.warning("飞书客户端未配置")
        return None
    except Exception as e:
        logger.error(f"创建日历事件失败: {e}")
        return None
