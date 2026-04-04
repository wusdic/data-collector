"""
配置加载器
支持 YAML 和 JSON 格式配置文件
"""

import os
import yaml
import json
from typing import Any, Dict, Optional
from pathlib import Path


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认使用 default_config.yaml
        """
        if config_path is None:
            base_dir = Path(__file__).parent
            config_path = base_dir / "default_config.yaml"
        
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            suffix = self.config_path.suffix.lower()
            if suffix in ['.yaml', '.yml']:
                self._config = yaml.safe_load(f) or {}
            elif suffix == '.json':
                self._config = json.load(f)
            else:
                raise ValueError(f"不支持的配置文件格式: {suffix}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        支持点号分隔的嵌套键，如 'SEARCH.engines.google.enabled'
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        支持点号分隔的嵌套键
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()
    
    def save(self, path: Optional[str] = None) -> None:
        """
        保存配置到文件
        
        Args:
            path: 保存路径，默认覆盖原文件
        """
        save_path = Path(path) if path else self.config_path
        
        with open(save_path, 'w', encoding='utf-8') as f:
            suffix = save_path.suffix.lower()
            if suffix in ['.yaml', '.yml']:
                yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)
            elif suffix == '.json':
                json.dump(self._config, f, ensure_ascii=False, indent=2)
    
    def reload(self) -> None:
        """重新加载配置"""
        self._load_config()


# 全局配置实例
_config_loader: Optional[ConfigLoader] = None


def get_config(config_path: Optional[str] = None) -> ConfigLoader:
    """
    获取配置加载器实例（单例模式）
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        ConfigLoader实例
    """
    global _config_loader
    
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    
    return _config_loader


def reset_config() -> None:
    """重置配置加载器"""
    global _config_loader
    _config_loader = None
