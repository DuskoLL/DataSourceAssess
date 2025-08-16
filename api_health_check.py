#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API健康状况检查
验证修复后的API调用功能是否稳定工作
"""

import time
import json
from collections import defaultdict
from api_fallback_manager import APIFallbackManager
from data_extractors import get_extractor_for_category
from http_client import get_http_client


def test_api_health():
    """测试API健康状况"""
    print("🔍 API健康状况检查开始...")
    
    manager = APIFallbackManager()
    results = defaultdict(list)
    
    # 测试主要加密货币
    test_symbols = ['bitcoin', 'ethereum', 'cardano', 'ripple', 'dogecoin', 'solana']
    
    print(f"测试 {len(test_symbols)} 种加密货币，每种测试3次...")
    
    for symbol in test_symbols:
        print(f"\n📊 测试 {symbol.upper()}:")
        success_count = 0
        
        for attempt in range(3):
            try:
                price, latency, error, ts, headers = manager.get_price_with_fallback(symbol)
                
                if error is None and price is not None:
                    success_count += 1
                    results[symbol].append({
                        'success': True,
                        'price': price,
                        'latency': latency,
                        'error': None
                    })
                    print(f"  ✅ 尝试 {attempt+1}: 价格={price:.2f}, 延迟={latency:.2f}ms")
                else:
                    results[symbol].append({
                        'success': False,
                        'price': None,
                        'latency': latency,
                        'error': error
                    })
                    print(f"  ❌ 尝试 {attempt+1}: 错误={error}, 延迟={latency:.2f}ms")
                
                time.sleep(1)  # 避免请求过于频繁
                
            except Exception as e:
                results[symbol].append({
                    'success': False,
                    'price': None,
                    'latency': 0,
                    'error': str(e)
                })
                print(f"  💥 尝试 {attempt+1}: 异常={e}")
        
        success_rate = (success_count / 3) * 100
        print(f"  📈 成功率: {success_rate:.1f}% ({success_count}/3)")
    
    # 生成报告
    print("\n" + "="*60)
    print("📋 API健康状况总结报告")
    print("="*60)
    
    total_success = 0
    total_tests = 0
    
    for symbol, tests in results.items():
        successful_tests = [t for t in tests if t['success']]
        success_rate = len(successful_tests) / len(tests) * 100
        
        if successful_tests:
            avg_latency = sum(t['latency'] for t in successful_tests) / len(successful_tests)
            avg_price = sum(t['price'] for t in successful_tests) / len(successful_tests)
            print(f"{symbol.upper():>10}: {success_rate:5.1f}% 成功, 平均延迟: {avg_latency:6.1f}ms, 平均价格: ${avg_price:,.2f}")
        else:
            print(f"{symbol.upper():>10}: {success_rate:5.1f}% 成功, 无有效数据")
        
        total_success += len(successful_tests)
        total_tests += len(tests)
    
    overall_success_rate = (total_success / total_tests) * 100
    print("-" * 60)
    print(f"{'总体':>10}: {overall_success_rate:5.1f}% 成功 ({total_success}/{total_tests} 测试)")
    
    # 保存结果
    report_file = "state/reports/api_health_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': time.time(),
            'overall_success_rate': overall_success_rate,
            'total_successful_tests': total_success,
            'total_tests': total_tests,
            'detailed_results': dict(results)
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 详细报告已保存至: {report_file}")
    
    if overall_success_rate >= 80:
        print("🎉 API修复成功！系统运行稳定。")
        return True
    else:
        print("⚠️  API仍需进一步优化。")
        return False


def test_http_client_directly():
    """直接测试HTTP客户端"""
    print("\n🌐 直接测试HTTP客户端...")
    
    client = get_http_client()
    test_urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://api.coinbase.com/v2/exchange-rates?currency=BTC",
        "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
    ]
    
    success_count = 0
    
    for url in test_urls:
        try:
            data, latency, error, headers = client.get_json(url, timeout_sec=5.0)
            if error is None and data:
                print(f"✅ {url} - 成功 ({latency:.2f}ms)")
                success_count += 1
            else:
                print(f"❌ {url} - 失败: {error}")
        except Exception as e:
            print(f"💥 {url} - 异常: {e}")
    
    success_rate = (success_count / len(test_urls)) * 100
    print(f"\nHTTP客户端成功率: {success_rate:.1f}% ({success_count}/{len(test_urls)})")
    
    return success_rate >= 80


if __name__ == "__main__":
    # 运行健康检查
    api_healthy = test_api_health()
    http_healthy = test_http_client_directly()
    
    print("\n" + "="*60)
    print("🏁 最终结果")
    print("="*60)
    print(f"API备用系统: {'✅ 健康' if api_healthy else '❌ 需要修复'}")
    print(f"HTTP客户端: {'✅ 健康' if http_healthy else '❌ 需要修复'}")
    
    if api_healthy and http_healthy:
        print("\n🎊 恭喜！所有API修复都已成功，系统可以稳定运行！")
    else:
        print("\n🔧 部分组件仍需进一步优化。")
