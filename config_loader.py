#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置文件加载器
支持YAML配置文件和环境变量覆盖
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class NetworkConfig:
    timeout_sec: float = 5.0
    retries: int = 3
    concurrent_requests: int = 10


@dataclass
class ClusteringConfig:
    k: int = 5
    algorithm: str = "kmeans"
    max_iterations: int = 100
    tolerance: float = 1e-4
    cache_enabled: bool = True
    cache_ttl_sec: int = 300


@dataclass
class EvaluationWeights:
    accuracy: float = 0.30
    availability: float = 0.15
    response_time: float = 0.15
    volatility: float = 0.10
    update_frequency: float = 0.10
    integrity: float = 0.10
    error_rate: float = 0.05
    historical: float = 0.05


@dataclass
class GradeThresholds:
    A_plus: float = 90.0
    A: float = 80.0
    B: float = 70.0
    C: float = 60.0


@dataclass
class EvaluationConfig:
    weights: EvaluationWeights = field(default_factory=EvaluationWeights)
    grade_thresholds: GradeThresholds = field(default_factory=GradeThresholds)
    availability_floor: float = 10.0


@dataclass
class MiningConfig:
    interval_sec: int = 60
    quorum: int = 3
    cluster_sample_size: int = 1
    enable_random_update: bool = False


@dataclass
class ProposalConfig:
    poll_interval_sec: float = 2.0


@dataclass
class StorageConfig:
    state_dir: str = "state"
    backup_enabled: bool = True
    backup_interval_sec: int = 3600


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_enabled: bool = True
    file_path: str = "logs/oracle.log"
    console_enabled: bool = True
    max_file_size_mb: int = 10
    backup_count: int = 5


@dataclass
class VirtualSourcesConfig:
    count: int = 1000
    update_probability: float = 0.1
    noise_range: float = 2.0


@dataclass
class PerformanceConfig:
    enable_metrics: bool = True
    metrics_interval_sec: int = 30


@dataclass
class OracleConfig:
    network: NetworkConfig = field(default_factory=NetworkConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    mining: MiningConfig = field(default_factory=MiningConfig)
    proposal: ProposalConfig = field(default_factory=ProposalConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    virtual_sources: VirtualSourcesConfig = field(default_factory=VirtualSourcesConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)


def _parse_yaml_simple(content: str) -> Dict[str, Any]:
    """简单的YAML解析器，仅支持基本结构（避免依赖外部库）"""
    result = {}
    current_section = result
    section_stack = [result]
    
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        # 检查缩进级别
        indent_level = (len(line) - len(line.lstrip())) // 2
        
        # 调整section_stack到正确的级别
        while len(section_stack) > indent_level + 1:
            section_stack.pop()
        current_section = section_stack[-1]
        
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            if not value:  # 这是一个新的section
                new_section = {}
                current_section[key] = new_section
                section_stack.append(new_section)
            else:
                # 解析值
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.replace('.', '').replace('-', '').isdigit():
                    value = float(value) if '.' in value else int(value)
                elif value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                
                current_section[key] = value
    
    return result


def _set_nested_value(obj: Any, path: str, value: Any) -> None:
    """设置嵌套对象的值"""
    parts = path.split('.')
    current = obj
    
    for part in parts[:-1]:
        if hasattr(current, part):
            current = getattr(current, part)
        else:
            return
    
    if hasattr(current, parts[-1]):
        # 转换类型以匹配原有类型
        original_value = getattr(current, parts[-1])
        if isinstance(original_value, bool):
            value = str(value).lower() == 'true'
        elif isinstance(original_value, int):
            value = int(value)
        elif isinstance(original_value, float):
            value = float(value)
        
        setattr(current, parts[-1], value)


def load_config(config_path: str = "config.yaml") -> OracleConfig:
    """加载配置文件"""
    config = OracleConfig()
    
    # 1. 从YAML文件加载配置（如果存在）
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_data = _parse_yaml_simple(f.read())
            
            # 递归更新配置
            def update_config_from_dict(cfg_obj: Any, data_dict: Dict[str, Any], prefix: str = ""):
                for key, value in data_dict.items():
                    if hasattr(cfg_obj, key):
                        attr = getattr(cfg_obj, key)
                        if hasattr(attr, '__dict__') and isinstance(value, dict):
                            # 嵌套对象
                            update_config_from_dict(attr, value, f"{prefix}{key}.")
                        else:
                            # 基本类型
                            if isinstance(attr, bool):
                                value = value if isinstance(value, bool) else str(value).lower() == 'true'
                            elif isinstance(attr, int):
                                value = int(value)
                            elif isinstance(attr, float):
                                value = float(value)
                            
                            setattr(cfg_obj, key, value)
            
            update_config_from_dict(config, yaml_data)
            
        except Exception as e:
            print(f"警告：无法加载配置文件 {config_path}: {e}")
    
    # 2. 环境变量覆盖（格式：ORACLE_SECTION_KEY=value）
    for key, value in os.environ.items():
        if key.startswith('ORACLE_'):
            config_path = key[7:].lower().replace('_', '.')  # 移除ORACLE_前缀
            _set_nested_value(config, config_path, value)
    
    return config


# 全局配置实例
_global_config: Optional[OracleConfig] = None


def get_config() -> OracleConfig:
    """获取全局配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = load_config()
    return _global_config


def reload_config(config_path: str = "config.yaml") -> OracleConfig:
    """重新加载配置"""
    global _global_config
    _global_config = load_config(config_path)
    return _global_config


if __name__ == "__main__":
    # 测试配置加载
    config = load_config()
    print("配置加载成功:")
    print(f"网络超时: {config.network.timeout_sec}s")
    print(f"聚类K值: {config.clustering.k}")
    print(f"准确度权重: {config.evaluation.weights.accuracy}")
    print(f"日志级别: {config.logging.level}")
