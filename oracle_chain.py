#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Oracle Data Source Evaluation Chain (重构版本)

这是重构后的核心模块，使用了模块化设计：
- 配置管理: config_loader.py
- 日志系统: logger.py
- HTTP客户端: http_client.py
- 数据提取: data_extractors.py
- 聚类算法: clustering.py
- 存储层: storage.py

这个文件现在主要包含：
- 核心数据结构（DataSource, Vote, Proposal, Block等）
- 业务逻辑（ProposerNode, MinerNode, ChainState等）
- 评估算法
- 向后兼容的API
"""

from __future__ import annotations

import hashlib
import statistics
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Callable, Deque, Dict, List, Optional, Tuple, Any
import os
import random

# 新模块导入
from config_loader import get_config, OracleConfig
from logger import get_logger, LoggerContext
from http_client import get_http_client, http_get_json
from data_extractors import (
    get_extractor, get_extractor_for_category, 
    extract_value_from_json, DataExtractor
)
from clustering import (
    get_clustering_manager, kmeans_fit_predict, 
    cluster_labels_to_grades, hash_cluster_result,
    features_vector_from_vote
)
from storage import get_storage, load_json_file, save_json_file, ensure_dirs


# ===============================
# 核心数据结构
# ===============================

@dataclass
class DataSource:
    """数据源定义"""
    key: str
    url: str
    category: str = "unknown"
    created_by: str = "system"
    last_label: Optional[str] = None
    last_score: Optional[float] = None
    last_price: Optional[float] = None
    last_latency_ms: Optional[float] = None
    last_deviation_ratio: Optional[float] = None
    last_eval_time: Optional[float] = None
    
    # 历史数据窗口
    success_history: Deque[bool] = field(default_factory=lambda: deque(maxlen=50))
    deviation_history: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    latency_history: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    freshness_history: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    server_ts_history: Deque[float] = field(default_factory=lambda: deque(maxlen=50))
    eval_time_history: Deque[float] = field(default_factory=lambda: deque(maxlen=50))


@dataclass
class Vote:
    """投票记录"""
    node_id: str
    label: str
    deviation_ratio: float
    price: Optional[float]
    latency_ms: float
    score: float
    data_fresh_ms: Optional[float]
    server_ts_ms: Optional[float]
    features: Optional[Dict[str, float]] = None
    error: Optional[str] = None


@dataclass
class Proposal:
    """提案"""
    proposal_id: str
    proposer_id: str
    kind: str  # "ADD", "UPDATE", "CLUSTER"
    source_key: str
    timestamp: float
    decided_label: Optional[str] = None
    votes: List[Vote] = field(default_factory=list)


@dataclass
class Block:
    """区块"""
    index: int
    timestamp: float
    previous_hash: str
    miner_id: str
    proposals: List[Proposal] = field(default_factory=list)
    block_hash: str = ""


# ===============================
# 文件路径管理
# ===============================

def get_config_aware_paths():
    """获取配置感知的路径"""
    config = get_config()
    # 使用绝对路径，避免与存储层的 base_dir 叠加导致出现 state/state 目录
    base_dir = os.path.abspath(config.storage.state_dir)
    
    return {
        "STATE_DIR": base_dir,
        "PROPOSALS_DIR": os.path.join(base_dir, "proposals"),
        "CHAIN_FILE": os.path.join(base_dir, "chain.json"),
        "REGISTRY_FILE": os.path.join(base_dir, "data_sources.json"),
        "VIRTUAL_FILE": os.path.join(base_dir, "virtual_sources.json"),
        "MASTER_FILE": os.path.join(base_dir, "master_table.json")
    }


# ===============================
# 评估算法
# ===============================

class EvaluationEngine:
    """评估引擎"""
    
    def __init__(self, config: Optional[OracleConfig] = None):
        self.config = config or get_config()
        self.logger = get_logger("evaluation", self.config)
        self.http_client = get_http_client()
        self.clustering = get_clustering_manager()
    
    def compute_reference_value(self, category: str, exclude_key: Optional[str] = None) -> Optional[float]:
        """计算参考价格（使用多源中位数）"""
        try:
            registry = load_registry()
            values = []
            
            for key, meta in registry.items():
                if key == exclude_key:
                    continue
                if not isinstance(meta, dict):
                    continue
                if meta.get("category") != category:
                    continue
                
                last_price = meta.get("last_price")
                if isinstance(last_price, (int, float)) and last_price > 0:
                    values.append(float(last_price))
            
            if len(values) >= 2:
                return statistics.median(values)
            
            # 回退到基准值
            return self.fetch_baseline_value(category)
            
        except Exception as e:
            self.logger.warning(f"计算参考价格失败: {e}")
            return self.fetch_baseline_value(category)
    
    def fetch_baseline_value(self, category: str) -> Optional[float]:
        """获取基准价格"""
        baseline_urls = {
            "bitcoin_price": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            "ethereum_price": "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            # 可以添加更多基准源
        }
        
        url = baseline_urls.get(category)
        if not url:
            return None
        
        try:
            data, _, err, _ = self.http_client.get_json(url, timeout_sec=3.0)
            if err or not data:
                return None
            
            if category == "bitcoin_price":
                return float(data.get("bitcoin", {}).get("usd", 0))
            elif category == "ethereum_price":
                return float(data.get("ethereum", {}).get("usd", 0))
            
        except Exception as e:
            self.logger.warning(f"获取基准价格失败 {category}: {e}")
        
        return None
    
    def _compute_composite_score(self, 
                                accuracy: float,
                                availability: float, 
                                response_time: float,
                                volatility: float,
                                update_frequency: float,
                                data_integrity: float,
                                error_rate: float,
                                historical_performance: float) -> float:
        """计算综合评分"""
        weights = self.config.evaluation.weights
        
        # 注意：response_time, volatility 已经是高分代表好性能的形式
        # error_rate 需要反向处理（低错误率更好）
        score = (
            accuracy * weights.accuracy +
            availability * weights.availability +
            response_time * weights.response_time +
            volatility * weights.volatility +
            update_frequency * weights.update_frequency +
            data_integrity * weights.integrity +
            (100.0 - error_rate) * weights.error_rate +  # 修复：对错误率取反
            historical_performance * weights.historical
        )
        
        return max(0.0, min(100.0, score))
    
    def evaluate_source(self, key: str, fetch_fn: Callable, data_source: Optional[DataSource] = None) -> Vote:
        """评估数据源"""
        node_id = getattr(self, 'node_id', 'evaluator')
        
        from logger import LoggerContext
        with LoggerContext(self.logger, f"evaluate_{key}"):
            # 获取数据源信息
            if data_source is None:
                registry = load_registry()
                ds_meta = registry.get(key, {})
                category = ds_meta.get("category", "unknown")
            else:
                category = data_source.category
                ds_meta = asdict(data_source)
            
            # 执行数据获取
            start_time = time.time()
            try:
                value, latency_ms, error, server_ts_ms, headers = fetch_fn()
                eval_time_ms = time.time() * 1000.0
            except Exception as e:
                self.logger.error(f"数据获取异常 {key}: {e}")
                floor_av = getattr(self.config.evaluation, 'availability_floor', 10.0)
                return Vote(
                    node_id=node_id,
                    label="D",
                    deviation_ratio=1.0,
                    price=None,
                    latency_ms=0.0,
                    score=0.0,
                    data_fresh_ms=None,
                    server_ts_ms=None,
                    features={
                        "accuracy": 0.0, "availability": float(floor_av), "response_time": 0.0,
                        "update_frequency": 0.0, "integrity": 0.0, 
                        "error_rate": 100.0, "historical": 0.0, "volatility": 0.0
                    },
                    error=str(e)
                )
        
            # 计算各项指标
            features = {}
            floor_av = getattr(self.config.evaluation, 'availability_floor', 10.0)
            
            # 1. 准确度 (基于与参考值的偏差) - 使用指数映射减少饱和
            deviation_ratio = 1.0
            if value is not None and error is None:
                ref_value = self.compute_reference_value(category, exclude_key=key)
                if ref_value and ref_value > 0:
                    deviation_ratio = abs(value - ref_value) / ref_value
            
            # 使用指数衰减映射，降低饱和效应: accuracy = 99.5 * exp(-k * deviation_ratio)
            # k=5 使得deviation_ratio=0.2时accuracy约60分，避免大量100分堆积
            import math
            accuracy = max(0.0, min(99.5, 99.5 * math.exp(-5.0 * deviation_ratio)))
            features["accuracy"] = accuracy
            
            # 2. 可用性 (基于历史成功率)
            success_history = ds_meta.get("success_history", [])
            if success_history:
                availability = 100.0 * sum(success_history) / len(success_history)
            else:
                availability = 100.0 if error is None else 0.0
            # 对异常/错误路径应用下限保护
            if error is not None:
                availability = max(float(floor_av), float(availability))
            features["availability"] = availability
            
            # 3. 响应时间
            response_time = max(0.0, 100.0 - min(100.0, latency_ms / 50.0))  # 5秒为满分
            features["response_time"] = response_time
            
            # 4. 更新频率 (基于数据新鲜度)
            update_frequency = 50.0  # 默认中等
            if server_ts_ms:
                age_ms = eval_time_ms - server_ts_ms
                update_frequency = max(0.0, 100.0 - min(100.0, age_ms / (60 * 1000)))  # 1分钟为满分
            features["update_frequency"] = update_frequency
            
            # 5. 数据完整性
            integrity = 100.0 if (value is not None and error is None) else 0.0
            features["integrity"] = integrity
            
            # 6. 错误率
            error_rate = 0.0 if error is None else 100.0
            features["error_rate"] = error_rate
            
            # 7. 历史表现
            deviation_history = ds_meta.get("deviation_history", [])
            if len(deviation_history) >= 2:
                try:
                    std_dev = statistics.pstdev(deviation_history)
                    historical = max(0.0, 100.0 - min(100.0, std_dev * 1000))
                except:
                    historical = 50.0
            else:
                historical = 50.0
            features["historical"] = historical
            
            # 8. 波动率 (基于响应时间和偏差历史的波动性)
            volatility = 50.0  # 默认中等
            latency_history = ds_meta.get("latency_history", [])
            if len(latency_history) >= 3:
                try:
                    # 使用响应时间的变异系数计算波动率
                    latency_mean = statistics.mean(latency_history)
                    latency_std = statistics.pstdev(latency_history)
                    if latency_mean > 0:
                        cv = latency_std / latency_mean  # 变异系数
                        volatility = max(0.0, 100.0 - min(100.0, cv * 100))  # 波动率越低越好
                except:
                    volatility = 50.0
            elif len(deviation_history) >= 3:
                try:
                    # 使用偏差历史的变异系数计算波动率
                    deviation_mean = statistics.mean(deviation_history)
                    deviation_std = statistics.pstdev(deviation_history) 
                    if deviation_mean > 0:
                        cv = deviation_std / deviation_mean
                        volatility = max(0.0, 100.0 - min(100.0, cv * 100))
                except:
                    volatility = 50.0
            features["volatility"] = volatility
            
            # 计算综合评分
            score = self._compute_composite_score(
                accuracy, availability, response_time, volatility,
                update_frequency, integrity, error_rate, historical
            )
            
            # 确定标签（暂时用阈值方法，实际会被聚类覆盖）
            thresholds = self.config.evaluation.grade_thresholds
            if score >= thresholds.A_plus:
                label = "A+"
            elif score >= thresholds.A:
                label = "A"
            elif score >= thresholds.B:
                label = "B"
            elif score >= thresholds.C:
                label = "C"
            else:
                label = "D"
            
            return Vote(
                node_id=node_id,
                label=label,
                deviation_ratio=deviation_ratio,
                price=value,
                latency_ms=latency_ms,
                score=score,
                data_fresh_ms=eval_time_ms - server_ts_ms if server_ts_ms else None,
                server_ts_ms=server_ts_ms,
                features=features,
                error=error
            )


# ===============================
# 节点实现
# ===============================

class ProposerNode:
    """提案节点"""
    
    def __init__(self, node_id: str, chain: Optional[Any] = None, config: Optional[OracleConfig] = None):
        self.node_id = node_id
        self.chain = chain
        self.config = config or get_config()
        self.logger = get_logger(f"proposer_{node_id}", self.config)
        self.evaluator = EvaluationEngine(self.config)
        self.evaluator.node_id = node_id
    
    def evaluate_source(self, key: str, fetch_fn: Callable) -> Vote:
        """评估数据源"""
        return self.evaluator.evaluate_source(key, fetch_fn)


class MinerNode:
    """矿工节点"""
    
    def __init__(self, node_id: str, chain: Any, proposers: List[ProposerNode], config: Optional[OracleConfig] = None):
        self.node_id = node_id
        self.chain = chain
        self.proposers = proposers
        self.config = config or get_config()
        self.logger = get_logger(f"miner_{node_id}", self.config)


class ChainState:
    """链状态管理"""
    
    def __init__(self, miner_id: str, quorum: int, config: Optional[OracleConfig] = None):
        self.miner_id = miner_id
        self.quorum = quorum
        self.config = config or get_config()
        self.logger = get_logger("chain", self.config)
        self.blocks: List[Block] = []
        self.data_sources: Dict[str, DataSource] = {}
    
    def add_block(self, proposals: List[Proposal]) -> Block:
        """添加新区块"""
        previous_hash = self.blocks[-1].block_hash if self.blocks else "genesis"
        
        block = Block(
            index=len(self.blocks),
            timestamp=time.time(),
            previous_hash=previous_hash,
            miner_id=self.miner_id,
            proposals=proposals
        )
        
        # 计算区块哈希
        block_data = f"{block.index}{block.timestamp}{block.previous_hash}{block.miner_id}"
        block.block_hash = hashlib.sha256(block_data.encode()).hexdigest()
        
        self.blocks.append(block)
        self.logger.info(f"新区块: 高度={block.index}, 哈希={block.block_hash[:12]}")
        
        return block


# ===============================
# 向后兼容的API
# ===============================

# 文件路径常量（向后兼容）
_paths = get_config_aware_paths()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = _paths["STATE_DIR"]
PROPOSALS_DIR = _paths["PROPOSALS_DIR"]
CHAIN_FILE = _paths["CHAIN_FILE"]
REGISTRY_FILE = _paths["REGISTRY_FILE"]
VIRTUAL_FILE = _paths["VIRTUAL_FILE"]
MASTER_FILE = _paths["MASTER_FILE"]


def load_registry() -> Dict[str, dict]:
    """加载数据源注册表"""
    return load_json_file(REGISTRY_FILE, default={})


def save_registry(registry: Dict[str, dict]) -> None:
    """保存数据源注册表"""
    save_json_file(REGISTRY_FILE, registry)


def load_virtual_sources() -> Dict[str, dict]:
    """加载虚拟数据源"""
    import json
    import os
    try:
        if os.path.exists(VIRTUAL_FILE):
            with open(VIRTUAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_virtual_sources(virt: Dict[str, dict]) -> None:
    """保存虚拟数据源"""
    save_json_file(VIRTUAL_FILE, virt)


def load_master_table() -> Dict[str, dict]:
    """加载主表"""
    return load_json_file(MASTER_FILE, default={"sources": {}, "rankings": {}})


def save_master_table(doc: Dict[str, dict]) -> None:
    """保存主表"""
    save_json_file(MASTER_FILE, doc)


def load_chain_doc() -> Dict[str, Any]:
    """加载链文档"""
    return load_json_file(CHAIN_FILE, default={"blocks": []})


def save_chain_doc(doc: Dict[str, Any]) -> None:
    """保存链文档"""
    save_json_file(CHAIN_FILE, doc)


def list_proposal_dirs() -> List[str]:
    """列出提案目录"""
    storage = get_storage()
    if not storage.file_exists("proposals"):
        return []
    
    dirs = []
    try:
        for item in storage.list_files("proposals"):
            item_path = os.path.join("proposals", item)
            if storage.file_exists(os.path.join(item_path, "proposal.json")):
                dirs.append(item_path)  # 返回相对路径，保持与load_json_file一致
    except:
        pass
    
    return dirs


def proposal_path(pid: str) -> str:
    """获取提案路径"""
    return os.path.join(PROPOSALS_DIR, pid)


def create_proposal(kind: str, source_key: str, proposer_id: str, meta: Optional[dict] = None) -> str:
    """创建提案"""
    pid = f"{int(time.time() * 1000)}-{source_key}-{kind}"
    pdir = proposal_path(pid)
    
    storage = get_storage()
    
    # 获取URL
    registry = load_registry()
    url = registry.get(source_key, {}).get("url", "")
    
    doc = {
        "proposal_id": pid,
        "kind": kind,
        "source_key": source_key,
        "url": url,
        "proposer_id": proposer_id,
        "timestamp": time.time(),
        "decided_label": None,
        "finalized": False,
    }
    
    if meta:
        doc.update(meta)
    
    storage.save_json(os.path.join(pdir.replace(STATE_DIR + "/", ""), "proposal.json"), doc)
    
    return pid


def iter_votes(pid: str) -> List[Dict[str, Any]]:
    """迭代投票"""
    votes_dir = os.path.join(proposal_path(pid), "votes")
    storage = get_storage()
    
    votes = []
    try:
        rel_votes_dir = votes_dir.replace(STATE_DIR + "/", "")
        for vote_file in storage.list_files(rel_votes_dir, "*.json"):
            vote_path = os.path.join(rel_votes_dir, vote_file)
            vote_data = storage.load_json(vote_path)
            if vote_data:
                votes.append(vote_data)
    except:
        pass
    
    return votes


def write_vote(pid: str, node_id: str, vote: Vote) -> None:
    """写入投票"""
    vote_path = os.path.join(proposal_path(pid), "votes", f"{node_id}.json")
    storage = get_storage()
    
    rel_vote_path = vote_path.replace(STATE_DIR + "/", "")
    storage.save_json(rel_vote_path, asdict(vote))


def mark_proposal_finalized(pid: str, decided_label: str, block_index: int) -> None:
    """标记提案已完成"""
    prop_path = os.path.join(proposal_path(pid), "proposal.json")
    storage = get_storage()
    
    rel_prop_path = prop_path.replace(STATE_DIR + "/", "")
    prop = storage.load_json(rel_prop_path)
    if prop:
        prop["finalized"] = True
        prop["decided_label"] = decided_label
        prop["block_index"] = block_index
        storage.save_json(rel_prop_path, prop)


def majority_decision(votes: List[Dict[str, Any]], quorum: int) -> Optional[str]:
    """多数决策"""
    if len(votes) < quorum:
        return None
    
    label_counts = {}
    for vote in votes:
        label = vote.get("label")
        if label:
            label_counts[label] = label_counts.get(label, 0) + 1
    
    if not label_counts:
        return None
    
    # 找到得票最多的标签
    max_count = max(label_counts.values())
    majority_labels = [label for label, count in label_counts.items() if count == max_count]
    
    # 需要过半数
    if max_count >= (len(votes) + 1) // 2:
        return majority_labels[0]  # 如果有并列，取第一个
    
    return None


def register_source(key: str, url: str, created_by: str = "system", category: str = "unknown") -> None:
    """注册数据源"""
    registry = load_registry()
    registry[key] = {
        "url": url,
        "category": category,
        "created_by": created_by,
        "created_at": time.time(),
        "label": None,
        "score": None,
        "last_price": None,
        "last_latency_ms": None,
        "last_deviation": None,
        "last_eval_time": None,
        "success_history": [],
        "deviation_history": [],
        "latency_history": [],
        "freshness_history": [],
        "server_ts_history": [],
        "eval_time_history": []
    }
    save_registry(registry)


def registry_fetch_fn(key: str) -> Optional[Callable]:
    """获取数据源获取函数"""
    registry = load_registry()
    source_meta = registry.get(key)
    
    if not source_meta:
        return None
    
    url = source_meta.get("url")
    category = source_meta.get("category", "unknown")
    
    if not url:
        return None
    
    # 创建获取函数
    def fetch_wrapper():
        extractor = get_extractor_for_category(category)
        return extractor.extract(url)
    
    return fetch_wrapper


# 内置数据源支持
BUILTIN_SOURCES = {}  # 保持向后兼容


def reset_registry_with_defaults(created_by: str = "system") -> None:
    """使用默认数据源重置注册表"""
    # 这里可以添加默认的数据源
    registry = {}
    save_registry(registry)


def bootstrap_registry_with_builtins() -> None:
    """使用内置源引导注册表"""
    # 保持向后兼容，但实际功能可能在其他地方实现
    pass


# 聚类相关的向后兼容API已在clustering.py中实现

def apply_cluster_results_to_master(
    master: Dict[str, dict],
    all_keys: List[str],
    all_grades: List[str],
    registry: Optional[Dict[str, dict]] = None,
    virtuals: Optional[Dict[str, dict]] = None,
) -> None:
    """应用聚类结果到主表"""
    GRADE_ORDER = ["A+", "A", "B", "C", "D"]
    
    def _grade_rank(g: str) -> int:
        try:
            return GRADE_ORDER.index(g)
        except Exception:
            return len(GRADE_ORDER) - 1
    
    # 更新每个源的等级
    now = time.time()
    for k, g in zip(all_keys, all_grades):
        if k not in master["sources"]:
            master["sources"][k] = {}
        master["sources"][k]["label"] = g
        master["sources"][k]["updated_at"] = now
        
        # 同步到 registry/virtual（若存在）
        if isinstance(registry, dict) and k in registry:
            registry[k]["label"] = g
            registry[k]["last_eval_time"] = now
        if isinstance(virtuals, dict) and k in virtuals:
            virtuals[k]["label"] = g
    
    # 计算各类别排名
    rankings: Dict[str, List[str]] = {}
    for key, meta in master["sources"].items():
        cat = meta.get("category")
        if not isinstance(cat, str):
            continue
        rankings.setdefault(cat, []).append(key)
    
    for cat, keys in rankings.items():
        keys.sort(key=lambda kk: _grade_rank(master["sources"].get(kk, {}).get("label", "D")))
    
    master["rankings"] = rankings


if __name__ == "__main__":
    print("Oracle Chain 重构版本 - 请运行 proposer_node.py 或 miner_node.py")
