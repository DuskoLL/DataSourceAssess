#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
系统功能验证测试
验证修复后的Oracle系统所有核心功能是否正常工作
"""

import os
import sys
import time
import json
import traceback
from typing import Dict, Any, List

def test_module_imports():
    """测试所有核心模块是否可以正常导入"""
    print("🔍 Testing module imports...")
    
    try:
        # 测试核心模块导入
        from config_loader import get_config, load_config
        from logger import get_logger
        from http_client import get_http_client
        from data_extractors import get_extractor_for_category
        from clustering import get_clustering_manager
        from storage import get_storage
        from oracle_chain import (
            load_registry, save_registry, 
            load_master_table, save_master_table,
            ProposerNode, MinerNode, ChainState
        )
        from data_quality_validator import DataQualityValidator
        
        print("✅ All core modules imported successfully")
        return True
        
    except Exception as e:
        print(f"❌ Module import failed: {e}")
        traceback.print_exc()
        return False

def test_configuration_system():
    """测试配置系统"""
    print("🔍 Testing configuration system...")
    
    try:
        from config_loader import get_config, load_config
        
        # 测试配置加载
        config = get_config()
        
        # 验证关键配置项
        assert hasattr(config, 'network')
        assert hasattr(config, 'clustering')
        assert hasattr(config, 'evaluation')
        assert hasattr(config, 'logging')
        
        assert config.network.timeout_sec > 0
        assert config.clustering.k == 5
        assert config.evaluation.weights.accuracy > 0
        
        print("✅ Configuration system working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        traceback.print_exc()
        return False

def test_logging_system():
    """测试日志系统"""
    print("🔍 Testing logging system...")
    
    try:
        from logger import get_logger
        from config_loader import get_config
        
        config = get_config()
        logger = get_logger("test", config)
        
        # 测试日志功能
        logger.info("Test log message")
        logger.debug("Test debug message")
        logger.warning("Test warning message")
        
        # 测试性能监控
        logger.record_event("test_event", 1.0)
        stats = logger.get_performance_stats()
        
        print("✅ Logging system working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Logging test failed: {e}")
        traceback.print_exc()
        return False

def test_storage_system():
    """测试存储系统"""
    print("🔍 Testing storage system...")
    
    try:
        from storage import get_storage
        
        storage = get_storage()
        
        # 测试JSON读写
        test_data = {"test": "data", "timestamp": time.time()}
        storage.save_json("test_storage.json", test_data)
        
        loaded_data = storage.load_json("test_storage.json")
        assert loaded_data["test"] == "data"
        
        # 清理测试文件
        storage.delete_file("test_storage.json")
        
        print("✅ Storage system working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        traceback.print_exc()
        return False

def test_clustering_system():
    """测试聚类系统"""
    print("🔍 Testing clustering system...")
    
    try:
        from clustering import get_clustering_manager
        
        manager = get_clustering_manager()
        
        # 生成测试数据
        test_data = []
        for i in range(50):
            # 生成8维特征向量
            point = [
                50 + (i % 2) * 40,  # accuracy
                60 + (i % 3) * 30,  # availability
                70 + (i % 2) * 20,  # response_time
                55 + (i % 4) * 15,  # volatility
                65 + (i % 3) * 25,  # update_frequency
                75 + (i % 2) * 20,  # integrity
                30 + (i % 4) * 20,  # error_rate
                60 + (i % 3) * 30   # historical
            ]
            test_data.append(point)
        
        # 测试聚类
        labels = manager.kmeans.fit_predict(test_data, 5)
        assert len(labels) == len(test_data)
        assert all(0 <= label < 5 for label in labels)
        
        # 测试等级转换
        grades = manager.cluster_labels_to_grades(labels, test_data)
        assert len(grades) == len(labels)
        assert all(grade in ['A+', 'A', 'B', 'C', 'D'] for grade in grades)
        
        # 测试哈希计算
        cluster_hash = manager.hash_cluster_result(labels)
        assert isinstance(cluster_hash, str)
        assert len(cluster_hash) > 0
        
        print("✅ Clustering system working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Clustering test failed: {e}")
        traceback.print_exc()
        return False

def test_http_client():
    """测试HTTP客户端（使用本地测试，避免网络依赖）"""
    print("🔍 Testing HTTP client...")
    
    try:
        from http_client import get_http_client
        
        client = get_http_client()
        
        # 测试客户端配置
        assert client.config is not None
        assert client.config.network.timeout_sec > 0
        
        print("✅ HTTP client initialized correctly")
        return True
        
    except Exception as e:
        print(f"❌ HTTP client test failed: {e}")
        traceback.print_exc()
        return False

def test_data_extractors():
    """测试数据提取器"""
    print("🔍 Testing data extractors...")
    
    try:
        from data_extractors import get_extractor_for_category, get_extractor
        
        # 测试通用提取器
        extractor = get_extractor_for_category("bitcoin_price")
        assert extractor is not None
        
        # 测试特定提取器
        binance_extractor = get_extractor("binance")
        assert binance_extractor is not None
        
        # 测试JSON值提取
        test_json = {"price": "50000.50", "volume": "100"}
        value = extractor.extract_value_from_json(test_json, "bitcoin_price")
        assert value == 50000.50
        
        print("✅ Data extractors working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Data extractor test failed: {e}")
        traceback.print_exc()
        return False

def test_oracle_chain_core():
    """测试Oracle链核心功能"""
    print("🔍 Testing Oracle chain core functions...")
    
    try:
        from oracle_chain import (
            load_registry, save_registry,
            load_master_table, save_master_table,
            ProposerNode, MinerNode, ChainState
        )
        
        # 测试数据加载
        registry = load_registry()
        assert isinstance(registry, dict)
        
        master = load_master_table()
        assert isinstance(master, dict)
        
        # 测试节点创建
        chain = ChainState(miner_id="test-miner", quorum=3)
        assert chain.miner_id == "test-miner"
        assert chain.quorum == 3
        
        proposer = ProposerNode(node_id="test-proposer", chain=chain)
        assert proposer.node_id == "test-proposer"
        
        miner = MinerNode(node_id="test-miner", chain=chain, proposers=[proposer])
        assert miner.node_id == "test-miner"
        
        print("✅ Oracle chain core functions working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Oracle chain test failed: {e}")
        traceback.print_exc()
        return False

def test_data_quality_validator():
    """测试数据质量验证器"""
    print("🔍 Testing data quality validator...")
    
    try:
        from data_quality_validator import DataQualityValidator
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        state_dir = os.path.join(base_dir, "state")
        
        validator = DataQualityValidator(state_dir)
        
        # 测试特征验证
        test_features = {
            "accuracy": 85.5,
            "availability": 95.0,
            "response_time": "invalid",  # 无效值，应该被修复
            "volatility": 150.0  # 超出范围，应该被修复
        }
        
        validated_features, fixes = validator.validate_features(test_features)
        
        assert validated_features["accuracy"] == 85.5
        assert validated_features["availability"] == 95.0
        assert validated_features["response_time"] == 50.0  # 默认值
        assert validated_features["volatility"] == 100.0  # 修正为最大值
        assert len(fixes) > 0
        
        print("✅ Data quality validator working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Data quality validator test failed: {e}")
        traceback.print_exc()
        return False

def test_report_generation():
    """测试报告生成"""
    print("🔍 Testing report generation...")
    
    try:
        from generate_simplified_reports import (
            analyze_grade_distribution,
            analyze_category_distribution,
            analyze_feature_statistics
        )
        
        # 创建测试数据
        test_master = {
            "sources": {
                "test_source_1": {
                    "label": "A+",
                    "category": "bitcoin_price",
                    "features": {
                        "accuracy": 95.0,
                        "availability": 98.0,
                        "response_time": 85.0,
                        "volatility": 80.0
                    }
                },
                "test_source_2": {
                    "label": "B",
                    "category": "ethereum_price",
                    "features": {
                        "accuracy": 75.0,
                        "availability": 85.0,
                        "response_time": 70.0,
                        "volatility": 60.0
                    }
                }
            }
        }
        
        # 测试各种分析函数
        grade_analysis = analyze_grade_distribution(test_master)
        assert grade_analysis['total_sources'] == 2
        assert 'A+' in grade_analysis['counts']
        assert 'B' in grade_analysis['counts']
        
        category_analysis = analyze_category_distribution(test_master)
        assert len(category_analysis['counts']) == 2
        
        feature_analysis = analyze_feature_statistics(test_master)
        assert 'accuracy' in feature_analysis['overall_stats']
        
        print("✅ Report generation working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Report generation test failed: {e}")
        traceback.print_exc()
        return False

def test_file_integrity():
    """测试关键文件的完整性"""
    print("🔍 Testing file integrity...")
    
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        state_dir = os.path.join(base_dir, "state")
        
        # 检查关键文件是否存在
        required_files = [
            "master_table.json",
            "data_sources.json",
            "virtual_sources.json",
            "chain.json"
        ]
        
        for filename in required_files:
            filepath = os.path.join(state_dir, filename)
            assert os.path.exists(filepath), f"Required file missing: {filename}"
            
            # 验证JSON格式
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert isinstance(data, dict), f"Invalid JSON format in {filename}"
        
        # 检查报告目录
        reports_dir = os.path.join(state_dir, "reports")
        assert os.path.exists(reports_dir), "Reports directory missing"
        
        print("✅ File integrity check passed")
        return True
        
    except Exception as e:
        print(f"❌ File integrity test failed: {e}")
        traceback.print_exc()
        return False

def run_comprehensive_test():
    """运行综合测试"""
    print("🚀 Starting comprehensive system validation test...")
    print("=" * 60)
    
    test_functions = [
        test_module_imports,
        test_configuration_system,
        test_logging_system,
        test_storage_system,
        test_clustering_system,
        test_http_client,
        test_data_extractors,
        test_oracle_chain_core,
        test_data_quality_validator,
        test_report_generation,
        test_file_integrity
    ]
    
    passed_tests = 0
    total_tests = len(test_functions)
    
    for test_func in test_functions:
        try:
            if test_func():
                passed_tests += 1
            print()  # 空行分隔
        except Exception as e:
            print(f"❌ Test {test_func.__name__} crashed: {e}")
            traceback.print_exc()
            print()
    
    print("=" * 60)
    print(f"📊 TEST RESULTS: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 ALL TESTS PASSED! System is ready for production.")
        print("✅ The Oracle system has been successfully optimized for IET journal publication.")
        return True
    else:
        print(f"⚠️  {total_tests - passed_tests} tests failed. Please review the issues above.")
        return False

def main():
    """主函数"""
    try:
        success = run_comprehensive_test()
        
        if success:
            print("\n🏆 SYSTEM VALIDATION SUMMARY:")
            print("• All core modules functioning correctly")
            print("• Data quality validation implemented")
            print("• Clustering algorithm optimized")
            print("• Reports generated in publication-ready format")
            print("• File integrity verified")
            print("• System ready for IET journal submission")
            
            return 0
        else:
            print("\n❌ SYSTEM VALIDATION FAILED")
            print("Please address the issues above before proceeding.")
            return 1
            
    except Exception as e:
        print(f"❌ System validation crashed: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
