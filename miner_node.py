#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
矿工节点（Miner）终端：
- 持续扫描 proposals 目录，聚合投票，达成多数门限则出块并更新链、注册表。
- 仅支持两种功能：
  1. 添加数据源API (ADD)：提案节点发起，矿工节点进行聚类评级并出块
  2. 维护系统数据源API评级 (CLUSTER)：矿工节点定期维护，更新特征并重新聚类

运行：
  python miner_node.py --id miner-1 --quorum 3
"""

from __future__ import annotations

import argparse
import os
import time
import random
import shutil
from typing import Dict, List
from dataclasses import asdict

from oracle_chain import (
    ChainState,
    MinerNode,
    Proposal,
    ProposerNode,
    create_proposal,
    load_registry,
    save_registry,
    load_virtual_sources,
    save_virtual_sources,
    list_proposal_dirs,
    load_json_file,
    save_json_file,
    iter_votes,
    proposal_path,
    mark_proposal_finalized,
    save_chain_doc,
    load_chain_doc,
    registry_fetch_fn,
    bootstrap_registry_with_builtins,
    features_vector_from_vote,
    kmeans_fit_predict,
    cluster_labels_to_grades,
    hash_cluster_result,
    load_master_table,
    save_master_table,
    apply_cluster_results_to_master,
    majority_decision,
    Block,  # 新增：用于重建历史区块
)


def save_chain_state(chain: ChainState) -> None:
    """保存链状态到chain.json文件"""
    chain_doc = {"blocks": []}
    for block in chain.blocks:
        block_dict = asdict(block)
        # 确保提案也被序列化
        block_dict["proposals"] = [asdict(p) for p in block.proposals]
        chain_doc["blocks"].append(block_dict)
    save_chain_doc(chain_doc)


def load_chain_state(chain: ChainState) -> None:
    """从持久化文件加载历史区块到内存中，保持链连续性"""
    try:
        doc = load_chain_doc()
        blocks = doc.get("blocks", []) if isinstance(doc, dict) else []
        if not blocks:
            print("[启动] 未发现历史区块，作为创世启动。")
            return
        restored = 0
        for b in blocks:
            if not isinstance(b, dict):
                continue
            # 重建 Proposal 对象列表（与save一致，未包含动态属性）
            proposals_data = b.get("proposals", [])
            proposals_objs: List[Proposal] = []
            for p in proposals_data:
                if isinstance(p, dict):
                    try:
                        proposals_objs.append(Proposal(**p))
                    except TypeError:
                        # 字段不匹配时进行必要的过滤
                        allow_keys = {"proposal_id", "proposer_id", "kind", "source_key", "timestamp", "decided_label", "votes"}
                        filtered = {k: v for k, v in p.items() if k in allow_keys}
                        proposals_objs.append(Proposal(**filtered))
            try:
                block_obj = Block(
                    index=int(b.get("index", 0)),
                    timestamp=float(b.get("timestamp", time.time())),
                    previous_hash=str(b.get("previous_hash", "genesis")),
                    miner_id=str(b.get("miner_id", "unknown")),
                    proposals=proposals_objs,
                    block_hash=str(b.get("block_hash", "")),
                )
                chain.blocks.append(block_obj)
                restored += 1
            except Exception as e:
                print(f"[启动] 恢复区块失败：{e}")
        if restored:
            tip = chain.blocks[-1].block_hash[:12] if chain.blocks and chain.blocks[-1].block_hash else ""
            print(f"[启动] 已加载历史区块 {restored} 个，当前高度={len(chain.blocks)-1} tip={tip}")
    except Exception as e:
        print(f"[启动] 加载历史链失败：{e}")


def reset_system_state():
    """重启时重置系统状态：清空历史数据，重新用data_sources和virtual_sources初始化"""
    print("[初始化] 重置系统状态...")
    
    # 1. 清空链状态
    empty_chain = {"blocks": []}
    save_chain_doc(empty_chain)
    print("[初始化] 已清空链状态")
    
    # 2. 清空历史日志
    log_path = "logs/oracle.log"
    if os.path.exists(log_path):
        try:
            with open(log_path, 'w') as f:
                f.write("")
            print("[初始化] 已清空历史日志")
        except Exception as e:
            print(f"[初始化] 清空日志失败: {e}")
    
    # 3. 清空proposals目录
    from oracle_chain import _paths
    proposals_dir = _paths["PROPOSALS_DIR"]
    if os.path.exists(proposals_dir):
        try:
            shutil.rmtree(proposals_dir)
            os.makedirs(proposals_dir, exist_ok=True)
            print("[初始化] 已清空提案历史")
        except Exception as e:
            print(f"[初始化] 清空提案历史失败: {e}")
    
    # 4. 从data_sources.json和virtual_sources.json重新初始化master表
    data_sources = load_registry()  # 加载data_sources.json
    virtual_sources = load_virtual_sources()  # 加载virtual_sources.json
    
    # 创建新的master表，将两部分数据作为初始数据
    master = {
        "sources": {},
        "rankings": {},
        "last_cluster_hash": ""
    }
    
    # 收集所有数据源的特征向量用于初始聚类
    all_points = []
    all_keys = []
    
    # 创建临时proposer用于评估真实数据源
    temp_chain = ChainState(miner_id="init", quorum=1)
    temp_proposer = ProposerNode(node_id="init-evaluator", chain=temp_chain)
    
    # 处理真实数据源
    for key, meta in data_sources.items():
        if not isinstance(meta, dict):
            continue
        
        category = meta.get("category", "unknown")
        master["sources"][key] = {
            "category": category,
            "label": meta.get("label", "D"),  # 使用现有评级或默认D级
            "updated_at": time.time()
        }
        
        # 提取特征（如果已有评估数据）
        features = {}
        last_deviation = meta.get("last_deviation")
        score = meta.get("score")
        last_latency_ms = meta.get("last_latency_ms")
        
        if (last_deviation is not None and score is not None and last_latency_ms is not None):
            # 基于已有评估数据构造特征
            try:
                s = float(score)
                # 根据score范围自适应缩放（兼容0-1与0-100两种刻度）
                if 0.0 <= s <= 1.0:
                    accuracy = max(0.0, min(100.0, s * 100.0))
                else:
                    accuracy = max(0.0, min(100.0, s))
                # 将偏差比（0~1）映射为可用性分，并与accuracy加权融合，避免极端0分
                dev = float(last_deviation)
                dev_ratio = max(0.0, min(1.0, dev))
                dev_score = 100.0 * (1.0 - dev_ratio)  # 0偏差→100，1偏差→0
                availability = max(0.0, min(100.0, 0.7 * accuracy + 0.3 * dev_score))
                # 延迟转响应时间：500ms≈50分；增加边界保护
                response_time = max(0.0, min(100.0, 100.0 - (float(last_latency_ms) / 10.0)))
                features = {
                    "accuracy": accuracy,
                    "availability": availability,
                    "response_time": response_time,
                    "volatility": 70.0,  # 默认值
                    "update_frequency": 80.0,  # 默认值
                    "integrity": 90.0,  # 默认值
                    "error_rate": 85.0,  # 默认值
                    "historical": 75.0,  # 默认值
                }
            except (ValueError, TypeError):
                # 转换失败，调用API获取真实评分
                features = None
        else:
            # 没有评估数据，调用API获取真实评分
            features = None
            
        # 如果没有有效特征，尝试调用真实API评估
        if features is None:
            print(f"[初始化] 为真实数据源 {key} 调用API获取评分...")
            fn = registry_fetch_fn(key)
            if fn is not None:
                try:
                    vote = temp_proposer.evaluate_source(key, fn)
                    if vote.features:
                        features = vote.features.copy()
                        # 更新registry中的评估数据
                        data_sources[key]["score"] = float(vote.score) if vote.score is not None else meta.get("score", 50.0)
                        data_sources[key]["last_deviation"] = vote.deviation_ratio if vote.deviation_ratio is not None else meta.get("last_deviation", 0.0)
                        data_sources[key]["last_latency_ms"] = vote.latency_ms if vote.latency_ms is not None else meta.get("last_latency_ms", 0.0)
                        print(f"[初始化] {key} API评估完成，得分: {vote.score:.1f}")
                    else:
                        raise Exception("评估失败：features为空")
                except Exception as e:
                    print(f"[初始化] {key} API评估失败: {e}，使用默认特征")
                    features = {
                        "accuracy": 50.0,
                        "availability": 50.0,
                        "response_time": 50.0,
                        "volatility": 50.0,
                        "update_frequency": 50.0,
                        "integrity": 50.0,
                        "error_rate": 50.0,
                        "historical": 50.0,
                    }
            else:
                # 无法获取fetch函数，使用默认特征
                features = {
                    "accuracy": 50.0,
                    "availability": 50.0,
                    "response_time": 50.0,
                    "volatility": 50.0,
                    "update_frequency": 50.0,
                    "integrity": 50.0,
                    "error_rate": 50.0,
                    "historical": 50.0,
                }
        
        master["sources"][key]["features"] = features
        
        # 添加到聚类输入
        vec = [
            features["accuracy"],
            features["availability"],
            features["response_time"],
            float(features.get("volatility", 50.0)),
            features["update_frequency"],
            features["integrity"],
            features["error_rate"],
            features["historical"],
        ]
        all_points.append(vec)
        all_keys.append(key)
    
    # 处理虚拟数据源
    for key, meta in virtual_sources.items():
        if not isinstance(meta, dict):
            continue
        
        category = meta.get("category", "virtual_cluster")
        features = meta.get("features", {})
        
        master["sources"][key] = {
            "category": category,
            "features": features,
            "label": meta.get("label", "B"),  # 虚拟源默认B级
            "updated_at": time.time()
        }
        
        # 添加到聚类输入
        if isinstance(features, dict):
            vec = [
                float(features.get("accuracy", 50.0)),
                float(features.get("availability", 50.0)),
                float(features.get("response_time", 50.0)),
                float(features.get("volatility", 50.0)),
                float(features.get("update_frequency", 50.0)),
                float(features.get("integrity", 50.0)),
                float(features.get("error_rate", 50.0)),
                float(features.get("historical", 50.0)),
            ]
            all_points.append(vec)
            all_keys.append(key)
    
    # 执行初始聚类重新分级
    if all_points:
        labels = kmeans_fit_predict(all_points, k=5)
        grades = cluster_labels_to_grades(labels, all_points)
        digest = hash_cluster_result(labels)
        
        # 应用聚类结果
        apply_cluster_results_to_master(master, all_keys, grades, registry=data_sources, virtuals=virtual_sources)
        master["last_cluster_hash"] = digest
        
        print(f"[初始化] 完成初始聚类：{len(all_keys)}个数据源，聚类哈希={digest[:12]}")
    
    # 保存初始化后的数据（包括更新的API评估数据）
    save_master_table(master)
    save_registry(data_sources)  # 保存包含新评估数据的注册表
    save_virtual_sources(virtual_sources)
    
    print(f"[初始化] 系统重置完成，共加载 {len(data_sources)} 个真实数据源和 {len(virtual_sources)} 个虚拟数据源")
    print("[初始化] 系统状态重置完成，真实数据源评分已更新")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="miner-1", help="矿工节点ID")
    parser.add_argument("--quorum", type=int, default=3, help="多数门限")
    parser.add_argument("--maintenance-interval", type=int, default=60, help="维护间隔（秒）")
    parser.add_argument("--reset-state", action="store_true", help="启动时清空历史并重置系统（默认保留历史数据）")
    args = parser.parse_args()

    node_id = args.id
    quorum = args.quorum
    maintenance_interval = args.maintenance_interval

    # 根据参数决定是否重置
    if args.reset_state:
        reset_system_state()
    else:
        print("[启动] 保留历史数据（未启用 --reset-state）。")

    chain = ChainState(miner_id=node_id, quorum=quorum)
    # 尝试加载历史区块，确保延续链
    load_chain_state(chain)

    bootstrap_registry_with_builtins()
    
    # 内部Proposer仅用于特征更新时的评估
    proposers = [ProposerNode(node_id=f"internal-{i}", chain=chain) for i in range(1, 2)]
    miner = MinerNode(node_id=node_id, chain=chain, proposers=proposers)

    print(f"矿工节点启动: {node_id}，quorum={quorum}。聚类K值=5，维护间隔={maintenance_interval}秒。")

    try:
        # 启动后不立刻进入维护轮询，避免启动阶段触发外部API调用
        last_maintenance_ts: float = time.time()
        pending_cluster_pid: str | None = None
        last_cluster_hash: str | None = None
        while True:
            start = time.time()

            # 1) 处理提案达成共识
            for pdir in list_proposal_dirs():
                prop = load_json_file(os.path.join(pdir, "proposal.json"), default=None)
                if not isinstance(prop, dict):
                    continue
                if prop.get("finalized"):
                    continue
                pid = prop.get("proposal_id")
                kind = prop.get("kind")
                key = prop.get("source_key")
                if not isinstance(pid, str):
                    continue
                votes = iter_votes(pid)
                decided = majority_decision(votes, quorum)
                if decided is None:
                    continue

                if kind == "CLUSTER":
                    # 聚类提案：创建包含source_changes的提案并出块
                    cluster_hash = prop.get("cluster_hash", "")
                    affected_count = prop.get("affected_count", 0)
                    grade_changes = prop.get("grade_changes", {})
                    
                    p = Proposal(
                        proposal_id=pid,
                        proposer_id=node_id,
                        kind="CLUSTER",
                        source_key=str(prop.get("source_key", "cluster")),
                        timestamp=time.time(),
                    )
                    p.decided_label = decided
                    # 在提案中添加source_changes信息
                    p.source_changes = {
                        "type": "cluster_update",
                        "details": {
                            "affected_count": affected_count,
                            "grade_changes": grade_changes,
                            "cluster_hash": cluster_hash[:12]
                        }
                    }
                    
                    blk = chain.add_block([p])
                    # 保存链状态到文件
                    save_chain_state(chain)
                    mark_proposal_finalized(pid, decided_label=decided, block_index=blk.index)
                    print(f"[finalized+block] {pid} CLUSTER hash={cluster_hash[:12]} 块高={blk.index}")
                    
                    # 标记维护周期完成
                    if pending_cluster_pid == pid:
                        pending_cluster_pid = None
                        last_maintenance_ts = time.time()
                    continue

                # ADD提案：新增数据源，进行聚类评级并出块
                if kind == "ADD" and isinstance(key, str):
                    reg = load_registry()
                    virt = load_virtual_sources()
                    master = load_master_table()
                    
                    # 收集新增数据源的基本信息
                    source_url = prop.get("url", reg.get(key, {}).get("url", ""))
                    source_category = prop.get("category", reg.get(key, {}).get("category", "unknown"))
                    
                    # 更新新增源的元信息
                    cat = prop.get("category") or reg.get(key, {}).get("category")
                    if key not in master["sources"]:
                        master["sources"][key] = {"category": cat}
                    
                    # 获取或评估新增源的特征
                    feats = prop.get("features")
                    if not isinstance(feats, dict):
                        # 仅对非builtin源评估网络；builtin:// 源使用默认或回退特征
                        url_for_add = source_url or reg.get(key, {}).get("url", "")
                        if isinstance(url_for_add, str) and url_for_add.startswith("builtin://"):
                            feats = None  # 留给后续默认特征处理
                        else:
                            fn = registry_fetch_fn(key)
                            if fn is not None:
                                vtmp = proposers[0].evaluate_source(key, fn)
                                feats = vtmp.features
                    if isinstance(feats, dict):
                        master["sources"][key]["features"] = feats
                     
                    # 组装聚类输入（包含新增源）
                    real_points: List[List[float]] = []
                    real_keys: List[str] = []
                    for rk, rmeta in master["sources"].items():
                        f = rmeta.get("features")
                        if isinstance(f, dict):
                            vec = [
                                float(f.get("accuracy", 0.0)),
                                float(f.get("availability", 0.0)),
                                float(f.get("response_time", 0.0)),
                                float(f.get("volatility", 0.0)),
                                float(f.get("update_frequency", 0.0)),
                                float(f.get("integrity", 0.0)),
                                float(f.get("error_rate", 0.0)),
                                float(f.get("historical", 0.0)),
                            ]
                            real_points.append(vec)
                            real_keys.append(rk)
                    
                    virt_points: List[List[float]] = []
                    virt_keys: List[str] = []
                    for vk, vmeta in virt.items():
                        f = vmeta.get("features") if isinstance(vmeta, dict) else None
                        if isinstance(f, dict):
                            vec = [
                                float(f.get("accuracy", 0.0)),
                                float(f.get("availability", 0.0)),
                                float(f.get("response_time", 0.0)),
                                float(f.get("volatility", 0.0)),
                                float(f.get("update_frequency", 0.0)),
                                float(f.get("integrity", 0.0)),
                                float(f.get("error_rate", 0.0)),
                                float(f.get("historical", 0.0)),
                            ]
                            virt_points.append(vec)
                            virt_keys.append(vk)
                    
                    all_points = real_points + virt_points
                    if all_points:
                        # 使用k=5进行聚类（五类）
                        labels = kmeans_fit_predict(all_points, k=5)
                        grades = cluster_labels_to_grades(labels, all_points)
                        digest = hash_cluster_result(labels)
                        
                        # 应用聚类结果到master、registry和virtual_sources
                        apply_cluster_results_to_master(master, real_keys + virt_keys, grades, registry=reg, virtuals=virt)
                        master["last_cluster_hash"] = digest
                        save_master_table(master)
                        save_registry(reg)
                        save_virtual_sources(virt)
                        
                        # 对新增源的ADD提案出块
                        assigned_grade = master["sources"].get(key, {}).get("label", "B")
                        p = Proposal(
                            proposal_id=pid,
                            proposer_id=node_id,
                            kind="ADD",
                            source_key=key,
                            timestamp=time.time(),
                        )
                        p.decided_label = assigned_grade
                        # 在提案中添加source_changes信息
                        p.source_changes = {
                            "type": "add",
                            "details": {
                                "source_key": key,
                                "url": source_url,
                                "category": source_category,
                                "assigned_grade": assigned_grade
                            }
                        }
                        
                        blk = chain.add_block([p])
                        # 保存链状态到文件
                        save_chain_state(chain)
                        mark_proposal_finalized(pid, decided_label=assigned_grade, block_index=blk.index)
                        print(f"[finalized+block] {pid} ADD {key} -> {assigned_grade} 块高={blk.index} (cluster_hash={digest[:12]})")
                    continue

            # 2) 维护系统数据源API评级：每隔一段时间随机选择1个每一类等级最高的源API更新特征
            now_ts = time.time()
            if pending_cluster_pid is None and (now_ts - last_maintenance_ts) >= maintenance_interval:
                reg = load_registry()
                virt = load_virtual_sources()
                master = load_master_table()
                
                # 每类选择等级最高的1个数据源更新特征
                per_cat_best: Dict[str, str] = {}
                if master.get("rankings"):
                    for cat, keys in master["rankings"].items():
                        if keys:
                            per_cat_best[cat] = keys[0]  # 等级最高的
                else:
                    # 如果没有rankings，从registry推断每类的一个代表
                    for k, meta in reg.items():
                        if not isinstance(meta, dict):
                            continue
                        cat = meta.get("category")
                        if isinstance(cat, str) and cat not in per_cat_best:
                            per_cat_best[cat] = k
                
                # 记录更新前的等级
                old_grades = {}
                for cat, k in per_cat_best.items():
                    old_grades[k] = master.get("sources", {}).get(k, {}).get("label", "D")
                
                # 更新选中的真实数据源特征
                updated_sources = []
                for cat, k in per_cat_best.items():
                    # builtin:// 源不发起网络请求，改为本地抖动；其他源按需评估
                    url_k = reg.get(k, {}).get("url", "") if isinstance(reg.get(k, {}), dict) else ""
                    is_builtin = isinstance(url_k, str) and url_k.startswith("builtin://")
                    if is_builtin:
                        # 对master中的特征进行轻微抖动（若不存在则初始化为默认）
                        master.setdefault("sources", {}).setdefault(k, {"category": cat})
                        f = master["sources"][k].get("features", {})
                        if not isinstance(f, dict) or not f:
                            f = {"accuracy": 50.0, "availability": 50.0, "response_time": 50.0,
                                 "volatility": 50.0, "update_frequency": 50.0, "integrity": 50.0, "error_rate": 50.0, "historical": 50.0}
                        for feature_name in ("accuracy", "availability", "response_time", 
                                           "volatility", "update_frequency", "integrity", "error_rate", "historical"):
                            base = float(f.get(feature_name, 50.0))
                            f[feature_name] = max(0.0, min(100.0, base + random.uniform(-2.0, 2.0)))
                        master["sources"][k]["features"] = f
                        updated_sources.append(k)
                    else:
                        fn = registry_fetch_fn(k)
                        if fn is not None:
                            v = proposers[0].evaluate_source(k, fn)
                            master.setdefault("sources", {}).setdefault(k, {"category": cat})
                            master["sources"][k]["features"] = v.features or {}
                            updated_sources.append(k)
                        else:
                            # 如果是虚拟数据源，随机修改特征
                            if k in virt and isinstance(virt[k], dict):
                                f = virt[k].get("features", {})
                                for feature_name in ("accuracy", "availability", "response_time", 
                                                   "volatility", "update_frequency", "integrity", "error_rate", "historical"):
                                    base = float(f.get(feature_name, 50.0))
                                    f[feature_name] = max(0.0, min(100.0, base + random.uniform(-2.0, 2.0)))
                                virt[k]["features"] = f
                                updated_sources.append(k)
                
                # 组装所有数据源进行聚类
                real_points: List[List[float]] = []
                real_keys: List[str] = []
                for rk, rmeta in master.setdefault("sources", {}).items():
                    f = rmeta.get("features")
                    if isinstance(f, dict):
                        vec = [
                            float(f.get("accuracy", 0.0)),
                            float(f.get("availability", 0.0)),
                            float(f.get("response_time", 0.0)),
                            float(f.get("volatility", 0.0)),
                            float(f.get("update_frequency", 0.0)),
                            float(f.get("integrity", 0.0)),
                            float(f.get("error_rate", 0.0)),
                            float(f.get("historical", 0.0)),
                        ]
                        real_points.append(vec)
                        real_keys.append(rk)
                
                virt_points: List[List[float]] = []
                virt_keys: List[str] = []
                for vk, vmeta in virt.items():
                    f = vmeta.get("features") if isinstance(vmeta, dict) else None
                    if isinstance(f, dict):
                        vec = [
                            float(f.get("accuracy", 0.0)),
                            float(f.get("availability", 0.0)),
                            float(f.get("response_time", 0.0)),
                            float(f.get("volatility", 0.0)),
                            float(f.get("update_frequency", 0.0)),
                            float(f.get("integrity", 0.0)),
                            float(f.get("error_rate", 0.0)),
                            float(f.get("historical", 0.0)),
                        ]
                        virt_points.append(vec)
                        virt_keys.append(vk)
                
                all_points = real_points + virt_points
                if all_points:
                    # 使用k=5进行聚类（五类）
                    labels = kmeans_fit_predict(all_points, k=5)
                    grades = cluster_labels_to_grades(labels, all_points)
                    digest = hash_cluster_result(labels)
                    
                    if last_cluster_hash is not None and digest == last_cluster_hash:
                        # 聚类结果没有变化，忽略
                        last_maintenance_ts = now_ts
                        print(f"[maintenance] 聚类结果无变化（hash={digest[:12]}），忽略操作")
                    else:
                        # 聚类结果有变化，统计等级变化
                        new_grades = {}
                        grade_changes = {}
                        
                        # 应用聚类结果
                        apply_cluster_results_to_master(master, real_keys + virt_keys, grades, registry=reg, virtuals=virt)
                        
                        # 统计等级变化
                        for k in real_keys + virt_keys:
                            new_grade = master.get("sources", {}).get(k, {}).get("label", "D")
                            new_grades[k] = new_grade
                            if k in old_grades and old_grades[k] != new_grade:
                                grade_changes[new_grade] = grade_changes.get(new_grade, 0) + 1
                        
                        # 发起CLUSTER提案广播给提案节点
                        pid = create_proposal("CLUSTER", source_key="cluster", proposer_id=node_id, meta={
                            "cluster_hash": digest,
                            "affected_count": len(updated_sources),
                            "grade_changes": grade_changes,
                            "updated_sources": updated_sources,
                            "k": 5,
                        })
                        print(f"[maintenance] 发起聚类提案: {pid} hash={digest[:12]} affected={len(updated_sources)} changes={grade_changes}")
                        pending_cluster_pid = pid
                        last_cluster_hash = digest
                        
                        # 保存更新后的数据
                        master["last_cluster_hash"] = digest
                        save_master_table(master)
                        save_registry(reg)
                        save_virtual_sources(virt)

            # 控制循环频率
            elapsed = time.time() - start
            time.sleep(max(0.2, 1.0 - elapsed))

    except KeyboardInterrupt:
        print("退出。")


if __name__ == "__main__":
    main()


