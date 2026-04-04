"""
更新通知器
支持多种通知方式：飞书、邮件、Webhook等
"""

import logging
from typing import List, Dict, Any, Optional
import requests
import json

from .update_monitor import UpdateInfo

logger = logging.getLogger(__name__)


class Notifier:
    """更新通知器"""
    
    def __init__(self, notify_config: List[Dict[str, Any]]):
        """
        初始化通知器
        
        Args:
            notify_config: 通知配置列表
        """
        self.channels: List[Dict[str, Any]] = []
        self._init_channels(notify_config)
    
    def _init_channels(self, notify_config: List[Dict[str, Any]]) -> None:
        """初始化通知渠道"""
        for config in notify_config:
            channel_type = config.get('type', '').lower()
            enabled = config.get('enabled', True)
            
            if enabled:
                self.channels.append({
                    'type': channel_type,
                    'config': config,
                })
        
        logger.info(f"已加载 {len(self.channels)} 个通知渠道")
    
    def send(self, updates: List[UpdateInfo]) -> None:
        """
        发送通知
        
        Args:
            updates: 更新信息列表
        """
        if not updates:
            return
        
        for channel in self.channels:
            try:
                channel_type = channel['type']
                config = channel['config']
                
                if channel_type == 'feishu':
                    self._send_feishu(config, updates)
                elif channel_type == 'email':
                    self._send_email(config, updates)
                elif channel_type == 'webhook':
                    self._send_webhook(config, updates)
                elif channel_type == 'console':
                    self._send_console(updates)
                else:
                    logger.warning(f"未知通知类型: {channel_type}")
            
            except Exception as e:
                logger.error(f"发送通知失败 ({channel['type']}): {e}")
    
    def _send_feishu(self, config: Dict[str, Any], updates: List[UpdateInfo]) -> None:
        """发送飞书通知"""
        webhook = config.get('webhook', '')
        
        if not webhook:
            logger.warning("飞书 Webhook 未配置")
            return
        
        # 构建消息
        content = self._format_feishu_message(updates)
        
        payload = {
            'msg_type': 'text',
            'content': {
                'text': content
            }
        }
        
        try:
            response = requests.post(
                webhook,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(payload),
                timeout=10
            )
            response.raise_for_status()
            logger.info("飞书通知发送成功")
        except Exception as e:
            logger.error(f"飞书通知发送失败: {e}")
    
    def _format_feishu_message(self, updates: List[UpdateInfo]) -> str:
        """格式化飞书消息"""
        lines = ["📢 **资料更新提醒**\n"]
        
        for update in updates:
            priority_emoji = '🔴' if update.priority == 'high' else '🟡' if update.priority == 'normal' else '🟢'
            lines.append(f"{priority_emoji} **{update.source_name}**")
            lines.append(f"   类型: {update.change_type}")
            lines.append(f"   详情: {update.details}")
            lines.append(f"   链接: {update.url}\n")
        
        lines.append("---")
        lines.append("由 DataCollector 自动发送")
        
        return '\n'.join(lines)
    
    def _send_email(self, config: Dict[str, Any], updates: List[UpdateInfo]) -> None:
        """发送邮件通知"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        smtp_server = config.get('smtp_server', '')
        smtp_port = config.get('smtp_port', 587)
        sender = config.get('sender', '')
        receivers = config.get('receivers', [])
        
        if not all([smtp_server, sender, receivers]):
            logger.warning("邮件配置不完整")
            return
        
        # 构建邮件内容
        subject = f"资料更新提醒 - {len(updates)} 项更新"
        body = self._format_email_message(updates)
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = ', '.join(receivers)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                # 如果配置了密码
                password = config.get('password', '')
                if password:
                    server.login(sender, password)
                server.send_message(msg)
            
            logger.info("邮件通知发送成功")
        except Exception as e:
            logger.error(f"邮件通知发送失败: {e}")
    
    def _format_email_message(self, updates: List[UpdateInfo]) -> str:
        """格式化邮件内容"""
        html = """
        <html>
        <body>
        <h2>📢 资料更新提醒</h2>
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color: #f2f2f2;">
            <th>数据源</th>
            <th>类型</th>
            <th>详情</th>
            <th>链接</th>
        </tr>
        """
        
        for update in updates:
            priority_color = '#ffcccc' if update.priority == 'high' else '#fff3cd' if update.priority == 'normal' else '#d4edda'
            html += f"""
            <tr style="background-color: {priority_color};">
                <td><strong>{update.source_name}</strong></td>
                <td>{update.change_type}</td>
                <td>{update.details}</td>
                <td><a href="{update.url}">查看</a></td>
            </tr>
            """
        
        html += """
        </table>
        <p style="color: #666; margin-top: 20px;">
        ---<br>
        由 DataCollector 自动发送
        </p>
        </body>
        </html>
        """
        
        return html
    
    def _send_webhook(self, config: Dict[str, Any], updates: List[UpdateInfo]) -> None:
        """发送 Webhook 通知"""
        webhook_url = config.get('webhook_url', '')
        
        if not webhook_url:
            logger.warning("Webhook URL 未配置")
            return
        
        payload = {
            'updates': [
                {
                    'source': u.source_name,
                    'url': u.url,
                    'change_type': u.change_type,
                    'details': u.details,
                    'priority': u.priority,
                    'detected_at': u.detected_at.isoformat(),
                }
                for u in updates
            ],
            'total': len(updates),
        }
        
        try:
            response = requests.post(
                webhook_url,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(payload),
                timeout=10
            )
            response.raise_for_status()
            logger.info("Webhook 通知发送成功")
        except Exception as e:
            logger.error(f"Webhook 通知发送失败: {e}")
    
    def _send_console(self, updates: List[UpdateInfo]) -> None:
        """输出到控制台"""
        print("\n" + "=" * 50)
        print("📢 资料更新提醒")
        print("=" * 50)
        
        for update in updates:
            print(f"\n[{update.source_name}]")
            print(f"  类型: {update.change_type}")
            print(f"  详情: {update.details}")
            print(f"  链接: {update.url}")
        
        print("\n" + "=" * 50 + "\n")
