#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
聚类算法模块
提供优化的K-means聚类实现，支持缓存和性能监控
"""

import hashlib
import json
import time
import threading
from typing import List, Dict, Optional, Tuple, Any
from math import sqrt
import statistics

from logger import get_logger
from config_loader import get_config


class ClusterCache:
    """聚类结果缓存"""
    
    def __init__(self, ttl_sec: int = 300):
        self.cache: Dict[str, Tuple[List[int], float]] = {}  # hash -> (labels, timestamp)
        self.ttl_sec = ttl_sec
        self.lock = threading.Lock()
    
    def _compute_hash(self, data: List[List[float]], k: int) -> str:
        """计算数据的哈希值"""
        # 将数据序列化为字符串并计算MD5
        data_str = json.dumps(data, sort_keys=True)
        hash_input = f"{data_str}:k={k}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def get(self, data: List[List[float]], k: int) -> Optional[List[int]]:
        """从缓存获取聚类结果"""
        cache_key = self._compute_hash(data, k)
        
        with self.lock:
            if cache_key in self.cache:
                labels, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.ttl_sec:
                    return labels.copy()
                else:
                    # 缓存过期，删除
                    del self.cache[cache_key]
        
        return None
    
    def put(self, data: List[List[float]], k: int, labels: List[int]):
        """将聚类结果放入缓存"""
        cache_key = self._compute_hash(data, k)
        
        with self.lock:
            self.cache[cache_key] = (labels.copy(), time.time())
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
    
    def cleanup_expired(self):
        """清理过期缓存"""
        current_time = time.time()
        with self.lock:
            expired_keys = [
                key for key, (_, timestamp) in self.cache.items()
                if current_time - timestamp >= self.ttl_sec
            ]
            for key in expired_keys:
                del self.cache[key]


class OptimizedKMeans:
    """优化的K-means聚类算法"""
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config or get_config()
        self.logger = get_logger("clustering", self.config)
        self.cache = ClusterCache(self.config.clustering.cache_ttl_sec) if self.config.clustering.cache_enabled else None
    
    def _distance(self, p1: List[float], p2: List[float]) -> float:
        """计算两点间欧氏距离"""
        if len(p1) != len(p2):
            raise ValueError(f"点的维度不匹配: {len(p1)} vs {len(p2)}")
        
        distance_squared = sum((a - b) ** 2 for a, b in zip(p1, p2))
        # 添加数值稳定性检查
        if distance_squared < 0:
            distance_squared = 0.0
        
        return sqrt(distance_squared)
    
    def _compute_centroid(self, points: List[List[float]]) -> List[float]:
        """计算质心"""
        if not points:
            return []
        
        dim = len(points[0])
        centroid = [0.0] * dim
        
        for point in points:
            for i in range(dim):
                centroid[i] += point[i]
        
        for i in range(dim):
            centroid[i] /= len(points)
        
        return centroid
    
    def _initialize_centroids(self, data: List[List[float]], k: int) -> List[List[float]]:
        """使用K-means++算法初始化质心"""
        if not data or k <= 0:
            return []
        
        centroids = []
        
        # 随机选择第一个质心
        import random
        centroids.append(data[random.randint(0, len(data) - 1)].copy())
        
        # 选择其余质心
        for _ in range(1, min(k, len(data))):
            distances = []
            for point in data:
                min_dist = min(self._distance(point, centroid) for centroid in centroids)
                distances.append(min_dist ** 2)
            
            # 基于距离平方的概率选择
            total_dist = sum(distances)
            if total_dist == 0:
                break
            
            prob = random.random() * total_dist
            cumulative = 0
            for i, dist in enumerate(distances):
                cumulative += dist
                if cumulative >= prob:
                    centroids.append(data[i].copy())
                    break
        
        return centroids
    
    def fit_predict(self, data: List[List[float]], k: int) -> List[int]:
        """执行K-means聚类并返回标签"""
        if not data:
            return []
        
        if k <= 0:
            return [0] * len(data)
        
        if k >= len(data):
            return list(range(len(data)))
        
        # 检查缓存
        if self.cache:
            cached_result = self.cache.get(data, k)
            if cached_result is not None:
                self.logger.debug(f"使用缓存的聚类结果，k={k}, 数据点={len(data)}")
                return cached_result
        
        start_time = time.time()
        
        try:
            # 初始化质心
            centroids = self._initialize_centroids(data, k)
            max_iterations = self.config.clustering.max_iterations
            tolerance = self.config.clustering.tolerance
            
            labels = [0] * len(data)
            
            for iteration in range(max_iterations):
                # 分配点到最近的质心
                new_labels = []
                for point in data:
                    distances = [self._distance(point, centroid) for centroid in centroids]
                    closest_centroid = distances.index(min(distances))
                    new_labels.append(closest_centroid)
                
                # 检查收敛
                if new_labels == labels:
                    self.logger.debug(f"K-means在第{iteration + 1}次迭代收敛")
                    break
                
                labels = new_labels
                
                # 更新质心
                new_centroids = []
                for i in range(k):
                    cluster_points = [data[j] for j in range(len(data)) if labels[j] == i]
                    if cluster_points:
                        new_centroids.append(self._compute_centroid(cluster_points))
                    else:
                        # 如果某个簇为空，保持原质心
                        new_centroids.append(centroids[i])
                
                # 检查质心变化
                centroid_shift = sum(
                    self._distance(old, new) 
                    for old, new in zip(centroids, new_centroids)
                )
                
                centroids = new_centroids
                
                if centroid_shift < tolerance:
                    self.logger.debug(f"K-means质心变化小于容差，在第{iteration + 1}次迭代收敛")
                    break
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.info(f"K-means聚类完成: k={k}, 数据点={len(data)}, 耗时={duration_ms:.2f}ms")
            
            # 缓存结果
            if self.cache:
                self.cache.put(data, k, labels)
            
            # 记录性能指标
            self.logger.record_event("clustering_operations")
            self.logger.performance.record_timing("clustering", duration_ms)
            
            return labels
            
        except Exception as e:
            self.logger.error(f"K-means聚类失败: {e}")
            # 返回默认标签
            return [i % k for i in range(len(data))]


class ClusteringManager:
    """聚类管理器"""
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config or get_config()
        self.logger = get_logger("clustering_manager", self.config)
        self.kmeans = OptimizedKMeans(self.config)
        self.grade_order = ["A+", "A", "B", "C", "D"]
    
    def cluster_labels_to_grades(self, labels: List[int], data_points: Optional[List[List[float]]] = None) -> List[str]:
        """将聚类标签转换为等级"""
        if not labels:
            return []
        
        unique_labels = list(set(labels))
        k = len(unique_labels)
        
        if k == 1:
            return ["B"] * len(labels)  # 只有一个簇，给中等评级
        
        # 如果没有数据点信息，使用原有的简单映射（向后兼容）
        if data_points is None or len(data_points) != len(labels):
            sorted_labels = sorted(unique_labels)
            label_to_grade = {}
            for i, label in enumerate(sorted_labels):
                if k == 5:
                    label_to_grade[label] = self.grade_order[i]
                else:
                    grade_index = min(int(i * len(self.grade_order) / k), len(self.grade_order) - 1)
                    label_to_grade[label] = self.grade_order[grade_index]
            return [label_to_grade[label] for label in labels]
        
        # 计算每个簇的质量分数（基于特征向量的加权平均）
        from config_loader import get_config
        config = get_config()
        weights = config.evaluation.weights
        
        cluster_scores = {}
        for label in unique_labels:
            # 收集该簇的所有数据点
            cluster_points = [data_points[i] for i in range(len(labels)) if labels[i] == label]
            if not cluster_points:
                cluster_scores[label] = 0.0
                continue
            
            # 计算簇的平均特征值（8个维度，增加 volatility）
            avg_features = [0.0] * 8
            for point in cluster_points:
                for j in range(min(8, len(point))):
                    avg_features[j] += point[j]
            
            for j in range(8):
                avg_features[j] /= len(cluster_points)
            
            # 计算综合质量分数（注意：error_rate需要取反）
            # 特征顺序：accuracy, availability, response_time, volatility, update_frequency, integrity, error_rate, historical
            score = (
                avg_features[0] * weights.accuracy +           # accuracy (高更好)
                avg_features[1] * weights.availability +       # availability (高更好)
                avg_features[2] * weights.response_time +      # response_time (高更好)
                avg_features[3] * weights.volatility +         # volatility (低波动性更好)
                avg_features[4] * weights.update_frequency +   # update_frequency (高更好)
                avg_features[5] * weights.integrity +          # integrity (高更好)
                (100.0 - avg_features[6]) * weights.error_rate +  # error_rate (低更好，所以取反)
                avg_features[7] * weights.historical           # historical (高更好)
            )
            cluster_scores[label] = score
        
        # 根据质量分数对簇进行排序（分数高的排在前面）
        sorted_labels_by_quality = sorted(unique_labels, key=lambda x: cluster_scores[x], reverse=True)
        
        # 映射到等级
        label_to_grade = {}
        for i, label in enumerate(sorted_labels_by_quality):
            if k == 5:
                label_to_grade[label] = self.grade_order[i]
            else:
                grade_index = min(int(i * len(self.grade_order) / k), len(self.grade_order) - 1)
                label_to_grade[label] = self.grade_order[grade_index]
        
        return [label_to_grade[label] for label in labels]
    
    def hash_cluster_result(self, labels: List[int]) -> str:
        """计算聚类结果的哈希值"""
        if not labels:
            return ""
        
        # 对标签排序以确保一致性
        sorted_labels = sorted(labels)
        labels_str = ",".join(map(str, sorted_labels))
        return hashlib.sha256(labels_str.encode()).hexdigest()
    
    def features_vector_from_vote(self, vote: Any) -> List[float]:
        """从投票对象提取特征向量"""
        if not hasattr(vote, 'features') or not vote.features:
            # 返回默认特征向量
            return [50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
        
        features = vote.features
        return [
            float(features.get("accuracy", 50.0)),
            float(features.get("availability", 50.0)),
            float(features.get("response_time", 50.0)),
            float(features.get("volatility", 50.0)),
            float(features.get("update_frequency", 50.0)),
            float(features.get("integrity", 50.0)),
            float(features.get("error_rate", 50.0)),
            float(features.get("historical", 50.0)),
        ]
    
    def cleanup_cache(self):
        """清理过期缓存"""
        if self.kmeans.cache:
            self.kmeans.cache.cleanup_expired()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取聚类性能统计"""
        return self.logger.get_performance_stats()


# 全局聚类管理器实例
_clustering_manager: Optional[ClusteringManager] = None
_manager_lock = threading.Lock()


def get_clustering_manager() -> ClusteringManager:
    """获取全局聚类管理器实例"""
    global _clustering_manager
    with _manager_lock:
        if _clustering_manager is None:
            _clustering_manager = ClusteringManager()
        return _clustering_manager


# 向后兼容的函数
def kmeans_fit_predict(data: List[List[float]], k: int) -> List[int]:
    """K-means聚类（向后兼容）"""
    manager = get_clustering_manager()
    return manager.kmeans.fit_predict(data, k)


def cluster_labels_to_grades(labels: List[int], data_points: Optional[List[List[float]]] = None) -> List[str]:
    """标签转等级（向后兼容）"""
    manager = get_clustering_manager()
    return manager.cluster_labels_to_grades(labels, data_points)


def hash_cluster_result(labels: List[int]) -> str:
    """聚类结果哈希（向后兼容）"""
    manager = get_clustering_manager()
    return manager.hash_cluster_result(labels)


def features_vector_from_vote(vote: Any) -> List[float]:
    """特征向量提取（向后兼容）"""
    manager = get_clustering_manager()
    return manager.features_vector_from_vote(vote)


if __name__ == "__main__":
    # 测试聚类算法
    from config_loader import load_config
    
    config = load_config()
    manager = ClusteringManager(config)
    
    # 生成测试数据
    import random
    random.seed(42)
    
    test_data = []
    for _ in range(100):
        point = [random.uniform(0, 100) for _ in range(7)]
        test_data.append(point)
    
    print("测试K-means聚类...")
    
    # 测试聚类
    start_time = time.time()
    labels = manager.kmeans.fit_predict(test_data, 5)
    duration = time.time() - start_time
    
    print(f"聚类完成: {len(test_data)} 数据点, 耗时: {duration * 1000:.2f}ms")
    print(f"标签分布: {dict(zip(*zip(*[(l, labels.count(l)) for l in set(labels)])))}") 
    
    # 测试等级转换
    grades = manager.cluster_labels_to_grades(labels, test_data)
    grade_counts = {grade: grades.count(grade) for grade in set(grades)}
    print(f"等级分布: {grade_counts}")
    
    # 测试哈希
    cluster_hash = manager.hash_cluster_result(labels)
    print(f"聚类哈希: {cluster_hash[:12]}...")
    
    # 测试缓存
    print("\n测试缓存...")
    start_time = time.time()
    cached_labels = manager.kmeans.fit_predict(test_data, 5)  # 应该从缓存获取
    cached_duration = time.time() - start_time
    
    print(f"缓存结果: 耗时: {cached_duration * 1000:.2f}ms")
    print(f"结果一致: {labels == cached_labels}")
    
    # 性能统计
    stats = manager.get_performance_stats()
    print(f"\n性能统计: {stats}")
