#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生成 1000 条虚拟数据源 API 特征并保存到 state/virtual_sources.json。

说明：
- 仅生成特征，不访问网络；与真实数据源分离存储。
- 特征包含八项（0-100）：accuracy、availability、response_time、volatility、update_frequency、integrity、error_rate、historical。
- 保证每个评估等级（A+/A/B/C/D）均有样本：通过混合不同分布生成。
"""

import os
import json
import random
import time

BASE_DIR = os.path.dirname(__file__)
STATE_DIR = os.path.join(BASE_DIR, "state")
VIRTUAL_FILE = os.path.join(STATE_DIR, "virtual_sources.json")


def ensure_dirs() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)


def save_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def synth_feature_set(target_grade: str) -> dict:
    """生成更真实的特征分布：具有相关性，避免过多100分"""
    # 基础配置：调整均值范围以获得更分散的分布
    cfg = {
        "A+": {"mu": 87, "sigma": 6},   # 降低A+均值，增加离散度
        "A": {"mu": 78, "sigma": 8},    # 调整A级分布
        "B": {"mu": 68, "sigma": 10},   # 调整B级分布
        "C": {"mu": 55, "sigma": 12},   # 调整C级分布
        "D": {"mu": 38, "sigma": 15},   # 调整D级分布
    }
    mu = cfg[target_grade]["mu"]
    sg = cfg[target_grade]["sigma"]
    
    # 生成主要特征，引入负相关（准确性高的往往延迟稍高）
    base_quality = random.gauss(mu, sg)
    
    # accuracy: 核心指标，与目标等级密切相关
    acc = clamp(base_quality + random.gauss(0, sg * 0.3))
    
    # availability: 与accuracy正相关，但有独立噪声
    avail = clamp(0.7 * acc + 0.3 * random.gauss(mu, sg) + random.gauss(0, sg * 0.4))
    
    # response_time: 与accuracy弱负相关（高精度可能需要更多计算时间）
    resp_penalty = max(0, (acc - 50) * 0.15)  # 准确性越高，响应时间稍低
    resp = clamp(random.gauss(mu, sg) - resp_penalty + random.gauss(0, sg * 0.5))
    
    # volatility: 与accuracy负相关（准确性高的数据源波动性通常较低）
    vola = clamp(100 - 0.4 * acc + random.gauss(mu * 0.6, sg))
    
    # update_frequency: 与availability正相关
    upd = clamp(0.6 * avail + 0.4 * random.gauss(mu, sg))
    
    # integrity: 与accuracy强正相关
    integ = clamp(0.8 * acc + 0.2 * random.gauss(mu, sg))
    
    # error_rate: 与accuracy、availability负相关（错误率低意味着质量高）
    err = clamp(100 - 0.5 * (acc + avail) + random.gauss(40, sg))
    
    # historical: 综合历史表现，与多个指标相关
    hist = clamp(0.4 * acc + 0.3 * avail + 0.2 * integ + 0.1 * (100 - vola) + random.gauss(0, sg * 0.6))
    
    return {
        "accuracy": round(acc, 1),
        "availability": round(avail, 1),
        "response_time": round(resp, 1),
        "volatility": round(vola, 1),
        "update_frequency": round(upd, 1),
        "integrity": round(integ, 1),
        "error_rate": round(err, 1),
        "historical": round(hist, 1),
    }


def main() -> None:
    ensure_dirs()
    # 目标：1000条，分布到五个等级
    plan = [
        ("A+", 150),
        ("A", 250),
        ("B", 300),
        ("C", 200),
        ("D", 100),
    ]
    virt = {}
    now = time.time()
    idx = 0
    for grade, count in plan:
        for _ in range(count):
            idx += 1
            key = f"virt_{grade}_{idx:04d}"
            feats = synth_feature_set(grade)
            virt[key] = {
                "category": "virtual_cluster",
                "created_at": now,
                "created_by": "generator",
                "label": None,  # 聚类后再填
                "score": None,
                "features": feats,
            }
    save_json(VIRTUAL_FILE, virt)
    print(f"虚拟数据源已生成: {len(virt)} 条 -> {VIRTUAL_FILE}")


if __name__ == "__main__":
    main()


