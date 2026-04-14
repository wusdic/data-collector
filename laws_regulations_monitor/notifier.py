"""
飞书通知器
发现新法规时通知用户
"""

import logging
import json
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LawsNotifier:
    """法律法规监控通知器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', True)
        self.feishu_open_id = config.get('feishu_open_id', '')

    def send(self, message: str) -> bool:
        """
        发送通知
        
        Args:
            message: 通知内容（Markdown 格式）
        """
        if not self.enabled:
            logger.info("通知已禁用")
            return True
        
        try:
            # 使用飞书 IM 发送消息
            self._send_feishu_message(message)
            logger.info("飞书通知发送成功")
            return True
        except Exception as e:
            logger.error(f"发送通知失败: {e}")
            return False

    def _send_feishu_message(self, content: str) -> None:
        """通过 OpenClaw 发送飞书消息"""
        try:
            # 导入 OpenClaw 的飞书消息工具
            import sys
            sys.path.insert(0, '/home/gem/workspace/agent/workspace')
            
            from message import message
            
            # 发送富文本消息
            result = message(
                action='send',
                channel='feishu',
                message=content
            )
            
            logger.info(f"飞书消息发送结果: {result}")
        
        except ImportError:
            # Fallback: 直接使用 requests
            logger.warning("OpenClaw message 工具不可用，尝试其他方式")
            self._send_via_webhook(content)

    def _send_via_webhook(self, content: str) -> None:
        """通过飞书 Webhook 发送"""
        webhook = self.config.get('webhook', '')
        if not webhook:
            logger.warning("未配置飞书 Webhook")
            return
        
        payload = {
            'msg_type': 'text',
            'content': {
                'text': content.replace('**', '').replace('•', '-').replace('🔹', '-')
            }
        }
        
        resp = requests.post(
            webhook,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload),
            timeout=10
        )
        resp.raise_for_status()

    def send_new_laws_alert(self, laws: list, level: str) -> None:
        """
        发送新法规提醒
        
        Args:
            laws: 新法规列表
            level: 层级标识
        """
        if not laws:
            return
        
        lines = [f"🆕 发现 **{len(laws)}** 条新增法规 ({level}):"]
        for law in laws[:10]:
            lines.append(f"  • {law}")
        
        if len(laws) > 10:
            lines.append(f"  ... 还有 {len(laws) - 10} 条")
        
        self.send('\n'.join(lines))
