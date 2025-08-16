#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
提案节点（Proposer）终端：
- 持续监控 proposals 目录的新提案，独立评估后写入 vote。
- 支持在终端输入 "add <key> <category> <url>" 动态新增数据源（写入注册表与ADD提案）。

运行：
  python proposer_node.py --id proposer-1

环境：仅标准库。
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Optional
import threading

from oracle_chain import (
    BUILTIN_SOURCES,
    ProposerNode,
    ChainState,
    create_proposal,
    iter_votes,
    write_vote,
    list_proposal_dirs,
    load_json_file,
    proposal_path,
    register_source,
    reset_registry_with_defaults,
    registry_fetch_fn,
    bootstrap_registry_with_builtins,
)


def handle_add_command(node_id: str, key: str, category: str, url: str) -> Optional[str]:
    # 注册数据源并创建ADD提案（需要指定类别）
    register_source(key, url, created_by=node_id, category=category)
    pid = create_proposal("ADD", key, proposer_id=node_id, meta={"category": category})
    print(f"已创建新增提案: {pid} for {key} [{category}] -> {url}")
    return pid


def interactive_loop(node_id: str) -> None:
    # 仅用于输入命令，非阻塞扫描逻辑在下方主循环
    while True:
        try:
            s = input()
        except EOFError:
            return
        s = s.strip()
        if not s:
            continue
        parts = s.split()
        if parts[0].lower() == "add" and len(parts) >= 4:
            key = parts[1]
            category = parts[2]
            url = " ".join(parts[3:])
            handle_add_command(node_id, key, category, url)
        elif parts[0].lower() == "addf" and len(parts) >= 4:
            # addf <key> <category> <url> ：提案节点本地抓取一次特征并附在ADD提案meta中
            key = parts[1]
            category = parts[2]
            url = " ".join(parts[3:])
            register_source(key, url, created_by=node_id, category=category)
            from oracle_chain import registry_fetch_fn, ProposerNode, ChainState
            chain = ChainState(miner_id="dummy", quorum=3)
            pn = ProposerNode(node_id=node_id, chain=chain)
            fn = registry_fetch_fn(key)
            feats = None
            if fn is not None:
                v = pn.evaluate_source(key, fn)
                feats = v.features
            pid = create_proposal("ADD", key, proposer_id=node_id, meta={"category": category, "features": feats})
            print(f"已创建新增提案(带特征): {pid} for {key} [{category}] -> {url}")
        else:
            print("未知命令。用法: add <key> <category> <url>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="proposer-1", help="节点ID")
    parser.add_argument("--poll", type=float, default=2.0, help="扫描提案间隔秒")
    parser.add_argument("--reset-seed", action="store_true", help="清空并用内置示例数据源初始化注册表")
    args = parser.parse_args()

    node_id = args.id
    poll = args.poll

    # 本地链状态仅用于 ProposerNode 内部稳定性指标（历史窗口），不会出块
    chain = ChainState(miner_id="dummy", quorum=3)
    proposer = ProposerNode(node_id=node_id, chain=chain)

    if args.reset_seed:
        reset_registry_with_defaults(created_by=node_id)
    bootstrap_registry_with_builtins()
    print(f"提案节点启动: {node_id}。输入 'add <key> <category> <url>' 新增数据源。")

    # 启动交互输入线程：允许用户随时键入 add <key> <url>
    t = threading.Thread(target=interactive_loop, args=(node_id,), daemon=True)
    t.start()

    # 主循环：扫描所有提案目录，若该节点尚未投票则投票
    try:
        last_seen = set()
        while True:
            time.sleep(poll)

            for pdir in list_proposal_dirs():
                pid = os.path.basename(pdir)
                prop = load_json_file(os.path.join(pdir, "proposal.json"), default=None)
                if not isinstance(prop, dict):
                    continue
                if prop.get("finalized"):
                    continue
                key = prop.get("source_key")
                if not isinstance(key, str):
                    continue

                kind = prop.get("kind")
                # 已投票检查（无论什么类型都先检查）
                voted = any(v.get("node_id") == node_id for v in iter_votes(pid))
                if voted:
                    continue

                if kind == "CLUSTER":
                    # 聚类提案：本地根据提案文件中的 cluster_hash 进行投票（简化为一致性确认）
                    ch = prop.get("cluster_hash")
                    if not isinstance(ch, str):
                        continue
                    from oracle_chain import Vote
                    v = Vote(node_id=node_id, label="A+", deviation_ratio=0.0, price=None, latency_ms=0.0, score=100.0, data_fresh_ms=None, server_ts_ms=None, features=None, error=None)
                    write_vote(pid, node_id, v)
                    print(f"已对聚类提案 {pid} 确认: hash={ch[:12]}")
                    continue
                else:
                    # 查找fetch函数
                    fn = registry_fetch_fn(key)
                    if fn is None:
                        if key in BUILTIN_SOURCES:
                            fn = BUILTIN_SOURCES[key].fetch  # type: ignore
                        else:
                            continue

                # 发起评估并写票
                vote = proposer.evaluate_source(key, fn)
                write_vote(pid, node_id, vote)
                print(f"已对提案 {pid} 投票: label={vote.label} score={vote.score}")

    except KeyboardInterrupt:
        print("退出。")


if __name__ == "__main__":
    main()


