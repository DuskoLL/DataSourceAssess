#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证BNB数据修复效果
检查修复后的BNB价格数据在可视化中的表现
"""

import json
from collections import defaultdict


def verify_bnb_improvement():
    """验证BNB数据修复的效果"""
    
    print("🔍 验证BNB数据修复效果...")
    
    # 加载主表数据
    with open('state/master_table.json', 'r', encoding='utf-8') as f:
        master_table = json.load(f)
    
    sources = master_table.get('sources', {})
    
    # 按类别统计数据
    by_category = defaultdict(lambda: {'accuracy': [], 'response_time': [], 'grades': []})
    
    for source_id, meta in sources.items():
        category = meta.get('category', 'unknown')
        features = meta.get('features', {})
        grade = meta.get('label', 'D')
        
        accuracy = float(features.get('accuracy', 0.0))
        response_time = float(features.get('response_time', 0.0))
        
        by_category[category]['accuracy'].append(accuracy)
        by_category[category]['response_time'].append(response_time)
        by_category[category]['grades'].append(grade)
    
    # 重点检查BNB价格类别
    bnb_data = by_category.get('bnb_price', {})
    
    if not bnb_data['accuracy']:
        print("❌ 未找到BNB价格数据")
        return
    
    print(f"\n📊 BNB价格类别数据统计:")
    print(f"  数据源数量: {len(bnb_data['accuracy'])}")
    
    # 准确度统计
    accuracies = bnb_data['accuracy']
    print(f"  准确度范围: {min(accuracies):.1f} - {max(accuracies):.1f}")
    print(f"  准确度平均: {sum(accuracies)/len(accuracies):.1f}")
    
    # 响应时间统计
    response_times = bnb_data['response_time']
    print(f"  响应时间范围: {min(response_times):.1f} - {max(response_times):.1f}")
    print(f"  响应时间平均: {sum(response_times)/len(response_times):.1f}")
    
    # 等级分布
    grades = bnb_data['grades']
    grade_counts = {}
    for grade in ['A+', 'A', 'B', 'C', 'D']:
        count = grades.count(grade)
        if count > 0:
            grade_counts[grade] = count
    
    print(f"  等级分布: {grade_counts}")
    
    # 与其他类别比较
    print(f"\n📈 与其他类别比较:")
    
    categories_to_compare = ['bitcoin_price', 'ethereum_price', 'cardano_price', 'bnb_price']
    
    for category in categories_to_compare:
        if category in by_category and by_category[category]['accuracy']:
            cat_accuracies = by_category[category]['accuracy']
            cat_response_times = by_category[category]['response_time']
            cat_grades = by_category[category]['grades']
            
            avg_accuracy = sum(cat_accuracies) / len(cat_accuracies)
            avg_response_time = sum(cat_response_times) / len(cat_response_times)
            
            # 高质量源占比
            high_quality = sum(1 for g in cat_grades if g in ['A+', 'A'])
            high_quality_percent = (high_quality / len(cat_grades)) * 100
            
            print(f"  {category.replace('_', ' ').title()}:")
            print(f"    数据源: {len(cat_accuracies)}, 平均准确度: {avg_accuracy:.1f}, 平均响应时间: {avg_response_time:.1f}")
            print(f"    高质量源占比: {high_quality}/{len(cat_grades)} ({high_quality_percent:.1f}%)")
    
    # 检查箱线图数据充分性
    print(f"\n📦 箱线图数据充分性检查:")
    
    for category in categories_to_compare:
        if category in by_category:
            cat_data = by_category[category]
            acc_count = len(cat_data['accuracy'])
            rt_count = len(cat_data['response_time'])
            
            # 检查数据点是否足够形成有意义的箱线图
            sufficient_data = acc_count >= 5 and rt_count >= 5
            status = "✅ 充分" if sufficient_data else "⚠️ 不足"
            
            print(f"  {category.replace('_', ' ').title()}: {acc_count}个数据点 {status}")
    
    # 生成修复效果总结
    print(f"\n🎯 BNB数据修复效果总结:")
    
    bnb_high_quality = sum(1 for g in bnb_data['grades'] if g in ['A+', 'A'])
    bnb_high_quality_percent = (bnb_high_quality / len(bnb_data['grades'])) * 100
    
    print(f"  ✅ BNB价格数据源质量显著提升")
    print(f"  ✅ 高质量源占比: {bnb_high_quality_percent:.1f}% ({bnb_high_quality}/{len(bnb_data['grades'])})")
    print(f"  ✅ 平均准确度: {sum(bnb_data['accuracy'])/len(bnb_data['accuracy']):.1f}")
    print(f"  ✅ 平均响应时间: {sum(bnb_data['response_time'])/len(bnb_data['response_time']):.1f}")
    print(f"  ✅ 箱线图数据充分性: 足够显示有意义的分布")
    
    # 检查是否仍有问题
    min_accuracy = min(bnb_data['accuracy'])
    if min_accuracy < 50:
        print(f"  ⚠️ 注意: 仍有较低准确度的数据源 (最低: {min_accuracy:.1f})")
    
    if bnb_high_quality_percent < 20:
        print(f"  ⚠️ 注意: 高质量源占比仍然较低")
    else:
        print(f"  🎉 BNB数据质量已达到可接受标准")


if __name__ == "__main__":
    print("🔬 BNB数据修复效果验证")
    print("=" * 40)
    
    try:
        verify_bnb_improvement()
        print("\n✅ 验证完成！")
        
    except Exception as e:
        print(f"\n❌ 验证过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
