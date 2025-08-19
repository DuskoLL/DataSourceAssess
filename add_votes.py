#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
为提案添加额外投票以满足法定人数要求
"""

from oracle_chain import Vote, write_vote

def add_extra_votes():
    """为现有提案添加额外投票"""
    
    # 为聚类提案添加投票
    cluster_vote_2 = Vote(
        node_id="proposer-2",
        label="A+",
        deviation_ratio=0.0,
        price=None,
        latency_ms=0.0,
        score=100.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error=None
    )
    
    cluster_vote_3 = Vote(
        node_id="proposer-3",
        label="A+",
        deviation_ratio=0.0,
        price=None,
        latency_ms=0.0,
        score=100.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error=None
    )
    
    # 为test_api提案添加投票
    test_api_vote_2 = Vote(
        node_id="proposer-2",
        label="B",
        deviation_ratio=0.3,
        price=None,
        latency_ms=500.0,
        score=75.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error="HTTP 401 Unauthorized"
    )
    
    test_api_vote_3 = Vote(
        node_id="proposer-3",
        label="B",
        deviation_ratio=0.3,
        price=None,
        latency_ms=480.0,
        score=72.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error="HTTP 401 Unauthorized"
    )
    
    try:
        # 添加聚类提案投票
        write_vote("1755588509005-cluster-CLUSTER", "proposer-2", cluster_vote_2)
        write_vote("1755588509005-cluster-CLUSTER", "proposer-3", cluster_vote_3)
        print("已为聚类提案添加proposer-2和proposer-3的投票")
        
        # 添加test_api提案投票
        write_vote("1755588511096-test_api-ADD", "proposer-2", test_api_vote_2)
        write_vote("1755588511096-test_api-ADD", "proposer-3", test_api_vote_3)
        print("已为test_api提案添加proposer-2和proposer-3的投票")
        
    except Exception as e:
        print(f"添加投票时出错: {e}")

def add_votes_for_new_proposal():
    """为新的real_time_test提案添加投票"""
    
    vote_2 = Vote(
        node_id="proposer-2",
        label="C",
        deviation_ratio=0.5,
        price=None,
        latency_ms=800.0,
        score=60.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error="Connection timeout"
    )
    
    vote_3 = Vote(
        node_id="proposer-3",
        label="C",
        deviation_ratio=0.5,
        price=None,
        latency_ms=750.0,
        score=65.0,
        data_fresh_ms=None,
        server_ts_ms=None,
        features=None,
        error="Connection timeout"
    )
    
    try:
        write_vote("1755589231801-real_time_test-ADD", "proposer-2", vote_2)
        write_vote("1755589231801-real_time_test-ADD", "proposer-3", vote_3)
        print("已为real_time_test提案添加proposer-2和proposer-3的投票")
    except Exception as e:
        print(f"添加投票时出错: {e}")

if __name__ == "__main__":
    add_extra_votes()
    add_votes_for_new_proposal()