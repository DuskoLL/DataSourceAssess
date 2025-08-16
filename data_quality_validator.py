#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Quality Validator for Oracle System
确保数据源和评估结果的质量，符合IET期刊发表标准
"""

import json
import os
import time
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
import statistics

def load_json_file(filepath: str) -> Optional[Dict[str, Any]]:
    """安全加载JSON文件"""
    try:
        if not os.path.exists(filepath):
            print(f"文件不存在: {filepath}")
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载文件失败 {filepath}: {e}")
        return None

def save_json_file(filepath: str, data: Dict[str, Any]) -> bool:
    """安全保存JSON文件"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存文件失败 {filepath}: {e}")
        return False

class DataQualityValidator:
    """数据质量验证器"""
    
    def __init__(self, state_dir: str = "state"):
        self.state_dir = state_dir
        self.validation_report = {
            "timestamp": time.time(),
            "issues_found": [],
            "fixes_applied": [],
            "statistics": {}
        }
    
    def validate_features(self, features: Dict[str, float]) -> Tuple[Dict[str, float], List[str]]:
        """验证和修复特征数据"""
        if not isinstance(features, dict):
            return {}, ["特征数据不是字典格式"]
        
        fixes = []
        validated_features = {}
        
        # 期望的特征名称和合理范围
        expected_features = {
            "accuracy": (0.0, 100.0),
            "availability": (0.0, 100.0), 
            "response_time": (0.0, 100.0),
            "volatility": (0.0, 100.0),
            "update_frequency": (0.0, 100.0),
            "integrity": (0.0, 100.0),
            "error_rate": (0.0, 100.0),
            "historical": (0.0, 100.0)
        }
        
        for feature_name, (min_val, max_val) in expected_features.items():
            value = features.get(feature_name)
            
            if value is None:
                # 缺失特征，使用默认值
                validated_features[feature_name] = 50.0
                fixes.append(f"缺失特征 {feature_name}，使用默认值 50.0")
            elif not isinstance(value, (int, float)):
                # 非数值特征，使用默认值
                validated_features[feature_name] = 50.0
                fixes.append(f"非数值特征 {feature_name}={value}，使用默认值 50.0")
            else:
                # 检查范围
                if value < min_val:
                    validated_features[feature_name] = min_val
                    fixes.append(f"特征 {feature_name} 值 {value} 低于最小值，修正为 {min_val}")
                elif value > max_val:
                    validated_features[feature_name] = max_val
                    fixes.append(f"特征 {feature_name} 值 {value} 高于最大值，修正为 {max_val}")
                else:
                    validated_features[feature_name] = float(value)
        
        return validated_features, fixes
    
    def validate_source_data(self, source_data: Dict[str, Any], source_key: str) -> Tuple[Dict[str, Any], List[str]]:
        """验证和修复单个数据源"""
        if not isinstance(source_data, dict):
            return {}, [f"数据源 {source_key} 数据格式错误"]
        
        validated_data = source_data.copy()
        fixes = []
        
        # 验证必要字段
        required_fields = ["category", "created_at", "created_by"]
        for field in required_fields:
            if field not in validated_data:
                if field == "category":
                    validated_data[field] = "unknown"
                elif field == "created_at":
                    validated_data[field] = time.time()
                elif field == "created_by":
                    validated_data[field] = "system"
                fixes.append(f"缺失字段 {field}，已添加默认值")
        
        # 验证数值字段
        numeric_fields = ["score", "last_latency_ms", "last_deviation"]
        for field in numeric_fields:
            if field in validated_data:
                value = validated_data[field]
                if value is not None and not isinstance(value, (int, float)):
                    try:
                        validated_data[field] = float(value)
                        fixes.append(f"转换 {field} 为数值: {value}")
                    except (ValueError, TypeError):
                        validated_data[field] = None
                        fixes.append(f"无法转换 {field}，设为 None")
        
        # 验证特征数据
        if "features" in validated_data:
            features, feature_fixes = self.validate_features(validated_data["features"])
            validated_data["features"] = features
            fixes.extend(feature_fixes)
        
        # 验证评级
        valid_grades = ["A+", "A", "B", "C", "D"]
        if "label" in validated_data:
            if validated_data["label"] not in valid_grades:
                validated_data["label"] = "C"  # 默认中等评级
                fixes.append(f"无效评级，设为默认值 C")
        
        return validated_data, fixes
    
    def validate_master_table(self) -> bool:
        """验证主表数据"""
        master_path = os.path.join(self.state_dir, "master_table.json")
        master = load_json_file(master_path)
        
        if not master:
            print("主表文件不存在或无法加载")
            return False
        
        total_fixes = 0
        sources = master.get("sources", {})
        
        for source_key, source_data in sources.items():
            validated_data, fixes = self.validate_source_data(source_data, source_key)
            sources[source_key] = validated_data
            total_fixes += len(fixes)
            
            if fixes:
                self.validation_report["fixes_applied"].extend([
                    f"[{source_key}] {fix}" for fix in fixes
                ])
        
        # 验证排名数据
        rankings = master.get("rankings", {})
        if not isinstance(rankings, dict):
            master["rankings"] = {}
            total_fixes += 1
            self.validation_report["fixes_applied"].append("修复排名数据格式")
        
        # 保存修复后的数据
        if total_fixes > 0:
            if save_json_file(master_path, master):
                print(f"主表验证完成，修复了 {total_fixes} 个问题")
                return True
            else:
                print("保存修复后的主表失败")
                return False
        else:
            print("主表验证完成，未发现问题")
            return True
    
    def validate_data_sources(self) -> bool:
        """验证数据源文件"""
        sources_path = os.path.join(self.state_dir, "data_sources.json")
        sources = load_json_file(sources_path)
        
        if not sources:
            print("数据源文件不存在或无法加载")
            return False
        
        total_fixes = 0
        
        for source_key, source_data in sources.items():
            validated_data, fixes = self.validate_source_data(source_data, source_key)
            sources[source_key] = validated_data
            total_fixes += len(fixes)
            
            if fixes:
                self.validation_report["fixes_applied"].extend([
                    f"[数据源-{source_key}] {fix}" for fix in fixes
                ])
        
        # 保存修复后的数据
        if total_fixes > 0:
            if save_json_file(sources_path, sources):
                print(f"数据源验证完成，修复了 {total_fixes} 个问题")
                return True
            else:
                print("保存修复后的数据源失败")
                return False
        else:
            print("数据源验证完成，未发现问题")
            return True
    
    def validate_virtual_sources(self) -> bool:
        """验证虚拟数据源"""
        virtual_path = os.path.join(self.state_dir, "virtual_sources.json")
        virtual = load_json_file(virtual_path)
        
        if not virtual:
            print("虚拟数据源文件不存在或无法加载")
            return False
        
        total_fixes = 0
        
        for source_key, source_data in virtual.items():
            validated_data, fixes = self.validate_source_data(source_data, source_key)
            virtual[source_key] = validated_data
            total_fixes += len(fixes)
            
            if fixes:
                self.validation_report["fixes_applied"].extend([
                    f"[虚拟源-{source_key}] {fix}" for fix in fixes
                ])
        
        # 保存修复后的数据
        if total_fixes > 0:
            if save_json_file(virtual_path, virtual):
                print(f"虚拟数据源验证完成，修复了 {total_fixes} 个问题")
                return True
            else:
                print("保存修复后的虚拟数据源失败")
                return False
        else:
            print("虚拟数据源验证完成，未发现问题")
            return True
    
    def generate_statistics(self) -> Dict[str, Any]:
        """生成数据统计信息"""
        stats = {}
        
        # 主表统计
        master_path = os.path.join(self.state_dir, "master_table.json")
        master = load_json_file(master_path)
        if master:
            sources = master.get("sources", {})
            stats["total_sources"] = len(sources)
            
            # 按类别统计
            category_counts = defaultdict(int)
            grade_counts = defaultdict(int)
            feature_completeness = []
            
            for source_data in sources.values():
                if isinstance(source_data, dict):
                    category = source_data.get("category", "unknown")
                    category_counts[category] += 1
                    
                    grade = source_data.get("label", "unknown")
                    grade_counts[grade] += 1
                    
                    features = source_data.get("features", {})
                    if isinstance(features, dict):
                        completeness = len(features) / 8.0 * 100  # 8个期望特征
                        feature_completeness.append(completeness)
            
            stats["categories"] = dict(category_counts)
            stats["grade_distribution"] = dict(grade_counts)
            
            if feature_completeness:
                stats["feature_completeness"] = {
                    "mean": statistics.mean(feature_completeness),
                    "min": min(feature_completeness),
                    "max": max(feature_completeness)
                }
        
        # 区块链统计
        chain_path = os.path.join(self.state_dir, "chain.json")
        chain = load_json_file(chain_path)
        if chain:
            blocks = chain.get("blocks", [])
            stats["total_blocks"] = len(blocks)
            
            if blocks:
                proposal_counts = defaultdict(int)
                for block in blocks:
                    if isinstance(block, dict):
                        proposals = block.get("proposals", [])
                        for proposal in proposals:
                            if isinstance(proposal, dict):
                                kind = proposal.get("kind", "unknown")
                                proposal_counts[kind] += 1
                
                stats["proposal_types"] = dict(proposal_counts)
        
        return stats
    
    def run_validation(self) -> bool:
        """运行完整的数据验证"""
        print("开始数据质量验证...")
        
        success = True
        
        # 验证各个数据文件
        success &= self.validate_master_table()
        success &= self.validate_data_sources()
        success &= self.validate_virtual_sources()
        
        # 生成统计信息
        self.validation_report["statistics"] = self.generate_statistics()
        
        # 保存验证报告
        report_path = os.path.join(self.state_dir, "validation_report.json")
        if save_json_file(report_path, self.validation_report):
            print(f"验证报告已保存到: {report_path}")
        
        print(f"数据质量验证完成。修复了 {len(self.validation_report['fixes_applied'])} 个问题")
        return success

def main():
    """主函数"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_dir = os.path.join(base_dir, "state")
    
    if not os.path.exists(state_dir):
        print(f"状态目录不存在: {state_dir}")
        return False
    
    validator = DataQualityValidator(state_dir)
    return validator.run_validation()

if __name__ == "__main__":
    success = main()
    if success:
        print("✅ 数据质量验证成功完成")
    else:
        print("❌ 数据质量验证中发现错误")
