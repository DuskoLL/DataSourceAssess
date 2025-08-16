#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化版系统报告生成器
不依赖matplotlib，生成文本格式的统计报告和简单的数据可视化
适用于IET期刊发表的数据分析报告
"""

import json
import os
import time
from collections import defaultdict
from typing import Dict, List, Any, Tuple

def load_json_file(filepath: str, default: Any = None) -> Any:
    """安全加载JSON文件"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {filepath}: {e}")
    return default

def generate_text_chart(data: List[Tuple[str, int]], title: str, max_width: int = 50) -> str:
    """生成ASCII文本图表"""
    if not data:
        return f"{title}\n(No data available)\n"
    
    # 排序数据
    sorted_data = sorted(data, key=lambda x: x[1], reverse=True)
    max_value = max(item[1] for item in sorted_data)
    
    chart = f"\n{title}\n" + "=" * len(title) + "\n"
    
    for label, value in sorted_data:
        # 计算条形长度
        bar_length = int((value / max_value) * max_width) if max_value > 0 else 0
        bar = "█" * bar_length
        
        # 格式化标签，确保对齐
        label_formatted = f"{label:<20}"
        chart += f"{label_formatted} |{bar:<{max_width}} {value}\n"
    
    return chart + "\n"

def analyze_grade_distribution(master: Dict[str, Any]) -> Dict[str, Any]:
    """分析等级分布"""
    sources = master.get('sources', {}) or {}
    
    grade_counts = defaultdict(int)
    total_sources = 0
    
    for source_data in sources.values():
        if isinstance(source_data, dict):
            grade = source_data.get('label', 'D')
            grade_counts[grade] += 1
            total_sources += 1
    
    # 按等级顺序排序
    grade_order = ['A+', 'A', 'B', 'C', 'D']
    ordered_counts = [(grade, grade_counts[grade]) for grade in grade_order if grade_counts[grade] > 0]
    
    return {
        'counts': dict(grade_counts),
        'ordered_counts': ordered_counts,
        'total_sources': total_sources,
        'percentages': {grade: (count / total_sources * 100) if total_sources > 0 else 0 
                       for grade, count in grade_counts.items()}
    }

def analyze_category_distribution(master: Dict[str, Any]) -> Dict[str, Any]:
    """分析类别分布"""
    sources = master.get('sources', {}) or {}
    
    category_counts = defaultdict(int)
    category_grades = defaultdict(lambda: defaultdict(int))
    
    for source_data in sources.values():
        if isinstance(source_data, dict):
            category = source_data.get('category', 'unknown')
            grade = source_data.get('label', 'D')
            
            category_counts[category] += 1
            category_grades[category][grade] += 1
    
    # 按数量排序
    ordered_counts = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    
    return {
        'counts': dict(category_counts),
        'ordered_counts': ordered_counts,
        'category_grades': dict(category_grades)
    }

def analyze_feature_statistics(master: Dict[str, Any]) -> Dict[str, Any]:
    """分析特征统计"""
    sources = master.get('sources', {}) or {}
    
    feature_stats = defaultdict(list)
    grade_features = defaultdict(lambda: defaultdict(list))
    
    for source_data in sources.values():
        if isinstance(source_data, dict):
            features = source_data.get('features', {})
            grade = source_data.get('label', 'D')
            
            if isinstance(features, dict):
                for feature_name, value in features.items():
                    if isinstance(value, (int, float)):
                        feature_stats[feature_name].append(float(value))
                        grade_features[grade][feature_name].append(float(value))
    
    # 计算统计指标
    stats = {}
    for feature_name, values in feature_stats.items():
        if values:
            stats[feature_name] = {
                'mean': sum(values) / len(values),
                'min': min(values),
                'max': max(values),
                'count': len(values)
            }
    
    # 按等级计算平均值
    grade_stats = {}
    for grade, features in grade_features.items():
        grade_stats[grade] = {}
        for feature_name, values in features.items():
            if values:
                grade_stats[grade][feature_name] = sum(values) / len(values)
    
    return {
        'overall_stats': stats,
        'grade_stats': grade_stats
    }

def analyze_blockchain_data(chain_doc: Dict[str, Any]) -> Dict[str, Any]:
    """分析区块链数据"""
    blocks = chain_doc.get('blocks', []) if isinstance(chain_doc, dict) else []
    
    if not blocks:
        return {'total_blocks': 0, 'proposal_types': {}, 'timeline': []}
    
    proposal_counts = defaultdict(int)
    timeline = []
    
    for block in blocks:
        if isinstance(block, dict):
            block_time = block.get('timestamp', 0)
            block_index = block.get('index', 0)
            timeline.append((block_index, block_time))
            
            proposals = block.get('proposals', [])
            for proposal in proposals:
                if isinstance(proposal, dict):
                    kind = proposal.get('kind', 'unknown')
                    proposal_counts[kind] += 1
    
    return {
        'total_blocks': len(blocks),
        'proposal_types': dict(proposal_counts),
        'timeline': timeline
    }

def generate_comprehensive_report(base_dir: str) -> str:
    """生成综合报告"""
    state_dir = os.path.join(base_dir, 'state')
    
    # 加载数据文件
    master = load_json_file(os.path.join(state_dir, 'master_table.json'), default={"sources": {}, "rankings": {}})
    chain_doc = load_json_file(os.path.join(state_dir, 'chain.json'), default={"blocks": []})
    validation_report = load_json_file(os.path.join(state_dir, 'validation_report.json'), default={})
    
    # 分析数据
    grade_analysis = analyze_grade_distribution(master)
    category_analysis = analyze_category_distribution(master)
    feature_analysis = analyze_feature_statistics(master)
    blockchain_analysis = analyze_blockchain_data(chain_doc)
    
    # 生成报告内容
    report = []
    
    # 报告头部
    report.append("=" * 80)
    report.append("Oracle Data Source Evaluation System - Comprehensive Analysis Report")
    report.append("Generated for IET Journal Publication")
    report.append(f"Report Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 80)
    report.append("")
    
    # 1. 系统概览
    report.append("1. SYSTEM OVERVIEW")
    report.append("-" * 40)
    report.append(f"Total Data Sources: {grade_analysis['total_sources']}")
    report.append(f"Total Categories: {len(category_analysis['counts'])}")
    report.append(f"Total Blocks Generated: {blockchain_analysis['total_blocks']}")
    
    if validation_report:
        fixes_count = len(validation_report.get('fixes_applied', []))
        report.append(f"Data Quality Issues Fixed: {fixes_count}")
    
    report.append("")
    
    # 2. 数据源等级分布
    report.append("2. DATA SOURCE QUALITY GRADE DISTRIBUTION")
    report.append("-" * 50)
    
    if grade_analysis['ordered_counts']:
        grade_chart_data = [(f"Grade {grade}", count) for grade, count in grade_analysis['ordered_counts']]
        report.append(generate_text_chart(grade_chart_data, "Quality Grade Distribution"))
        
        report.append("Grade Distribution Percentages:")
        for grade, percentage in grade_analysis['percentages'].items():
            if percentage > 0:
                report.append(f"  {grade}: {percentage:.1f}%")
    else:
        report.append("No grade distribution data available.")
    
    report.append("")
    
    # 3. 数据源类别分布
    report.append("3. DATA SOURCE CATEGORY DISTRIBUTION")
    report.append("-" * 45)
    
    if category_analysis['ordered_counts']:
        category_chart_data = [(cat.replace('_', ' ').title()[:15], count) 
                              for cat, count in category_analysis['ordered_counts']]
        report.append(generate_text_chart(category_chart_data, "Category Distribution"))
    else:
        report.append("No category distribution data available.")
    
    report.append("")
    
    # 4. 特征统计分析
    report.append("4. FEATURE STATISTICS ANALYSIS")
    report.append("-" * 40)
    
    if feature_analysis['overall_stats']:
        report.append("Overall Feature Statistics:")
        report.append(f"{'Feature':<20} {'Mean':<8} {'Min':<8} {'Max':<8} {'Count':<8}")
        report.append("-" * 60)
        
        for feature_name, stats in feature_analysis['overall_stats'].items():
            report.append(f"{feature_name:<20} {stats['mean']:<8.2f} {stats['min']:<8.2f} {stats['max']:<8.2f} {stats['count']:<8}")
        
        report.append("")
        
        # 按等级的特征平均值
        if feature_analysis['grade_stats']:
            report.append("Feature Averages by Quality Grade:")
            grade_order = ['A+', 'A', 'B', 'C', 'D']
            
            for grade in grade_order:
                if grade in feature_analysis['grade_stats']:
                    report.append(f"\n{grade} Grade Sources:")
                    grade_features = feature_analysis['grade_stats'][grade]
                    for feature_name, avg_value in grade_features.items():
                        report.append(f"  {feature_name}: {avg_value:.2f}")
    else:
        report.append("No feature statistics available.")
    
    report.append("")
    
    # 5. 区块链性能分析
    report.append("5. BLOCKCHAIN PERFORMANCE ANALYSIS")
    report.append("-" * 42)
    
    if blockchain_analysis['proposal_types']:
        proposal_chart_data = [(ptype, count) for ptype, count in blockchain_analysis['proposal_types'].items()]
        report.append(generate_text_chart(proposal_chart_data, "Proposal Types Distribution"))
    else:
        report.append("No blockchain data available.")
    
    # 6. 实验结果总结
    report.append("6. EXPERIMENTAL RESULTS SUMMARY")
    report.append("-" * 40)
    
    # 计算关键指标
    if grade_analysis['total_sources'] > 0:
        high_quality_sources = grade_analysis['counts'].get('A+', 0) + grade_analysis['counts'].get('A', 0)
        high_quality_percentage = (high_quality_sources / grade_analysis['total_sources']) * 100
        
        report.append(f"High Quality Sources (A+/A): {high_quality_sources} ({high_quality_percentage:.1f}%)")
        report.append(f"Medium Quality Sources (B): {grade_analysis['counts'].get('B', 0)}")
        report.append(f"Low Quality Sources (C/D): {grade_analysis['counts'].get('C', 0) + grade_analysis['counts'].get('D', 0)}")
        
        # 系统效率指标
        if feature_analysis['overall_stats']:
            accuracy_stats = feature_analysis['overall_stats'].get('accuracy', {})
            availability_stats = feature_analysis['overall_stats'].get('availability', {})
            response_time_stats = feature_analysis['overall_stats'].get('response_time', {})
            
            if accuracy_stats:
                report.append(f"Average System Accuracy: {accuracy_stats['mean']:.2f}")
            if availability_stats:
                report.append(f"Average System Availability: {availability_stats['mean']:.2f}")
            if response_time_stats:
                report.append(f"Average Response Time Score: {response_time_stats['mean']:.2f}")
    
    report.append("")
    
    # 7. 研究结论和建议
    report.append("7. RESEARCH CONCLUSIONS & RECOMMENDATIONS")
    report.append("-" * 48)
    
    report.append("Key Findings:")
    if grade_analysis['total_sources'] > 0:
        if high_quality_percentage > 60:
            report.append("• The oracle system demonstrates high effectiveness with majority of sources achieving A/A+ grades")
        elif high_quality_percentage > 30:
            report.append("• The oracle system shows moderate effectiveness with balanced quality distribution")
        else:
            report.append("• The oracle system requires optimization as low-quality sources dominate")
    
    if len(category_analysis['counts']) > 5:
        report.append("• Multi-category data source diversity enhances system robustness")
    
    if blockchain_analysis['total_blocks'] > 0:
        report.append(f"• Blockchain consensus mechanism successfully processed {blockchain_analysis['total_blocks']} blocks")
    
    report.append("")
    report.append("Recommendations for Future Research:")
    report.append("• Implement machine learning-based quality prediction models")
    report.append("• Enhance real-time monitoring and adaptive threshold mechanisms")
    report.append("• Expand evaluation framework to include additional quality metrics")
    report.append("• Investigate optimal cluster sizes for different data source categories")
    
    report.append("")
    
    # 8. 技术规格
    report.append("8. TECHNICAL SPECIFICATIONS")
    report.append("-" * 35)
    report.append("• Clustering Algorithm: K-means (K=5)")
    report.append("• Quality Metrics: 8-dimensional feature vector")
    report.append("• Consensus Mechanism: Majority voting with configurable quorum")
    report.append("• Data Processing: Real-time evaluation with caching")
    report.append("• Storage: JSON-based persistent state management")
    
    report.append("")
    report.append("=" * 80)
    report.append("End of Report")
    report.append("=" * 80)
    
    return "\n".join(report)

def create_summary_statistics_table() -> str:
    """创建汇总统计表格"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_dir = os.path.join(base_dir, 'state')
    
    master = load_json_file(os.path.join(state_dir, 'master_table.json'), default={"sources": {}})
    sources = master.get('sources', {})
    
    if not sources:
        return "No data available for statistics table."
    
    # 按等级统计
    grade_stats = defaultdict(lambda: {
        'count': 0,
        'accuracy': [],
        'availability': [],
        'response_time': [],
        'volatility': []
    })
    
    for source_data in sources.values():
        if isinstance(source_data, dict):
            grade = source_data.get('label', 'D')
            features = source_data.get('features', {})
            
            grade_stats[grade]['count'] += 1
            
            if isinstance(features, dict):
                for metric in ['accuracy', 'availability', 'response_time', 'volatility']:
                    value = features.get(metric)
                    if isinstance(value, (int, float)):
                        grade_stats[grade][metric].append(float(value))
    
    # 生成表格
    table = []
    table.append("\nSTATISTICAL SUMMARY TABLE FOR IET JOURNAL SUBMISSION")
    table.append("=" * 70)
    table.append(f"{'Grade':<8} {'Count':<8} {'Accuracy':<12} {'Availability':<14} {'Response':<12} {'Volatility':<12}")
    table.append(f"{'Level':<8} {'(n)':<8} {'(μ±σ)':<12} {'(μ±σ)':<14} {'Time(μ±σ)':<12} {'(μ±σ)':<12}")
    table.append("-" * 70)
    
    grade_order = ['A+', 'A', 'B', 'C', 'D']
    for grade in grade_order:
        if grade in grade_stats and grade_stats[grade]['count'] > 0:
            stats = grade_stats[grade]
            count = stats['count']
            
            # 计算平均值和标准差
            metrics_summary = []
            for metric in ['accuracy', 'availability', 'response_time', 'volatility']:
                values = stats[metric]
                if values:
                    mean = sum(values) / len(values)
                    if len(values) > 1:
                        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
                        std = variance ** 0.5
                    else:
                        std = 0.0
                    metrics_summary.append(f"{mean:.1f}±{std:.1f}")
                else:
                    metrics_summary.append("N/A")
            
            table.append(f"{grade:<8} {count:<8} {metrics_summary[0]:<12} {metrics_summary[1]:<14} {metrics_summary[2]:<12} {metrics_summary[3]:<12}")
    
    table.append("-" * 70)
    table.append(f"Total: {sum(stats['count'] for stats in grade_stats.values())} data sources")
    table.append("")
    
    return "\n".join(table)

def main():
    """主函数"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_dir = os.path.join(base_dir, 'state')
    reports_dir = os.path.join(state_dir, 'reports')
    
    # 确保报告目录存在
    os.makedirs(reports_dir, exist_ok=True)
    
    print("📊 Generating comprehensive text-based analysis reports...")
    
    # 生成综合报告
    comprehensive_report = generate_comprehensive_report(base_dir)
    
    # 生成统计表格
    statistics_table = create_summary_statistics_table()
    
    # 保存报告
    report_file = os.path.join(reports_dir, 'comprehensive_analysis_report.txt')
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(comprehensive_report)
        f.write("\n\n")
        f.write(statistics_table)
    
    print(f"✅ Comprehensive analysis report generated: {report_file}")
    
    # 生成简化的CSV数据用于外部可视化工具
    csv_file = os.path.join(reports_dir, 'data_summary.csv')
    generate_csv_data(base_dir, csv_file)
    print(f"✅ CSV data file generated: {csv_file}")
    
    # 输出关键统计信息到控制台
    print("\n" + "="*60)
    print("KEY FINDINGS SUMMARY")
    print("="*60)
    
    master = load_json_file(os.path.join(state_dir, 'master_table.json'), default={"sources": {}})
    sources = master.get('sources', {})
    
    if sources:
        grade_counts = defaultdict(int)
        for source_data in sources.values():
            if isinstance(source_data, dict):
                grade = source_data.get('label', 'D')
                grade_counts[grade] += 1
        
        total = sum(grade_counts.values())
        print(f"Total Data Sources Analyzed: {total}")
        
        for grade in ['A+', 'A', 'B', 'C', 'D']:
            count = grade_counts[grade]
            percentage = (count / total * 100) if total > 0 else 0
            print(f"Grade {grade}: {count} sources ({percentage:.1f}%)")
        
        high_quality = grade_counts['A+'] + grade_counts['A']
        high_quality_pct = (high_quality / total * 100) if total > 0 else 0
        print(f"\nHigh Quality Sources (A+/A): {high_quality_pct:.1f}%")
        
    print("="*60)
    print("Reports saved in state/reports/ directory")
    print("Ready for IET journal submission!")

def generate_csv_data(base_dir: str, csv_file: str):
    """生成CSV格式的数据用于外部可视化"""
    state_dir = os.path.join(base_dir, 'state')
    master = load_json_file(os.path.join(state_dir, 'master_table.json'), default={"sources": {}})
    sources = master.get('sources', {})
    
    if not sources:
        return
    
    with open(csv_file, 'w', encoding='utf-8') as f:
        # 写入表头
        f.write("source_id,category,grade,accuracy,availability,response_time,volatility,update_frequency,integrity,error_rate,historical\n")
        
        # 写入数据
        for source_id, source_data in sources.items():
            if isinstance(source_data, dict):
                category = source_data.get('category', 'unknown')
                grade = source_data.get('label', 'D')
                features = source_data.get('features', {})
                
                if isinstance(features, dict):
                    f.write(f"{source_id},{category},{grade}")
                    for feature in ['accuracy', 'availability', 'response_time', 'volatility', 
                                  'update_frequency', 'integrity', 'error_rate', 'historical']:
                        value = features.get(feature, 0.0)
                        f.write(f",{value}")
                    f.write("\n")

if __name__ == "__main__":
    main()
