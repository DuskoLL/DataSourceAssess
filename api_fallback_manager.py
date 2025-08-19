#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API备用管理器
提供API故障切换和备用端点管理功能
"""

import time
import random
from typing import Dict, List, Optional, Tuple, Any
from http_client import get_http_client
from logger import get_logger
from config_loader import get_config


class APIFallbackManager:
    """API备用管理器"""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger("api_fallback", self.config)
        self.http_client = get_http_client()
        
        # 备用API端点配置
        self.fallback_apis = {
            'bitcoin': [
                # 优先使用当前环境已验证可达的端点
                "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
                "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT",
                "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT",
                "https://api.kucoin.com/api/v1/market/stats?symbol=BTC-USDT",
                "https://api.gemini.com/v1/pubticker/btcusd",
                "https://www.bitstamp.net/api/v2/ticker/btcusd",
                "https://api-pub.bitfinex.com/v2/ticker/tBTCUSD",
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
                "https://min-api.cryptocompare.com/data/price?fsym=BTC&tsyms=USD",
                "https://api.binance.us/api/v3/ticker/price?symbol=BTCUSD",
                # 作为次级候选（当前环境可能不通或不稳定）
                "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=BTC"
            ],
            'ethereum': [
                # 优先使用当前环境已验证可达的端点（部分按逻辑推断）
                "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT",
                "https://api.bybit.com/v5/market/tickers?category=linear&symbol=ETHUSDT",
                "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=ETH_USDT",
                "https://api.kucoin.com/api/v1/market/stats?symbol=ETH-USDT",
                "https://api.gemini.com/v1/pubticker/ethusd",
                "https://www.bitstamp.net/api/v2/ticker/ethusd",
                "https://api-pub.bitfinex.com/v2/ticker/tETHUSD",
                "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
                "https://min-api.cryptocompare.com/data/price?fsym=ETH&tsyms=USD",
                "https://api.binance.us/api/v3/ticker/price?symbol=ETHUSD",
                # 次级候选
                "https://api.kraken.com/0/public/Ticker?pair=ETHUSD",
                "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=ETH"
            ],
            'cardano': [
                "https://api.binance.com/api/v3/ticker/price?symbol=ADAUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=ADA",
                "https://api.kraken.com/0/public/Ticker?pair=ADAUSD"
            ],
            'ripple': [
                "https://api.binance.com/api/v3/ticker/price?symbol=XRPUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=XRP",
                "https://api.kraken.com/0/public/Ticker?pair=XRPUSD"
            ],
            'dogecoin': [
                "https://api.binance.com/api/v3/ticker/price?symbol=DOGEUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=DOGE",
                "https://api.kraken.com/0/public/Ticker?pair=DOGEUSD"
            ],
            'solana': [
                "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=SOL",
                "https://api.kraken.com/0/public/Ticker?pair=SOLUSD"
            ],
            'tron': [
                "https://api.binance.com/api/v3/ticker/price?symbol=TRXUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=TRX"
            ],
            'polkadot': [
                "https://api.binance.com/api/v3/ticker/price?symbol=DOTUSDT",
                "https://api.coinbase.com/v2/exchange-rates?currency=DOT",
                "https://api.kraken.com/0/public/Ticker?pair=DOTUSD"
            ]
        }
        
        # API失败计数
        self.failure_counts = {}
        self.last_failure_time = {}
        
    def get_price_with_fallback(self, symbol: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        """使用备用API获取价格数据"""
        symbol_key = symbol.lower()
        
        if symbol_key not in self.fallback_apis:
            return None, 0.0, f"unsupported_symbol: {symbol}", None, {}
        
        apis = self.fallback_apis[symbol_key].copy()
        random.shuffle(apis)  # 随机化API顺序以分散负载
        
        total_start_time = time.time()
        last_error = None
        
        for api_url in apis:
            # 检查该API是否最近失败过
            if self._should_skip_api(api_url):
                continue
                
            start_time = time.time()
            
            try:
                data, latency, err, headers = self.http_client.get_json(api_url, timeout_sec=3.0)
                
                if err:
                    self._record_failure(api_url)
                    last_error = err
                    continue
                
                # 尝试解析不同API的响应格式
                price = self._extract_price_from_response(data, api_url)
                
                if price is not None:
                    self._record_success(api_url)
                    total_latency = (time.time() - total_start_time) * 1000.0
                    self.logger.debug(f"成功获取价格 {symbol}: {price} from {api_url}")
                    return price, total_latency, None, time.time() * 1000.0, headers
                else:
                    self._record_failure(api_url)
                    last_error = "price_not_found"
                    
            except Exception as e:
                self._record_failure(api_url)
                last_error = f"api_error: {e}"
                self.logger.warning(f"API调用失败 {api_url}: {e}")
        
        total_latency = (time.time() - total_start_time) * 1000.0
        self.logger.error(f"所有备用API都失败 {symbol}: {last_error}")
        return None, total_latency, last_error, None, {}
    
    def _extract_price_from_response(self, data: Dict[str, Any], api_url: str) -> Optional[float]:
        """从不同API响应中提取价格"""
        try:
            if 'binance.com' in api_url or 'binance.us' in api_url:
                return float(data.get('price', 0))
            
            elif 'coinbase.com' in api_url:
                rates = data.get('data', {}).get('rates', {})
                return float(rates.get('USD', 0))
            
            elif 'kraken.com' in api_url:
                result = data.get('result', {})
                for pair_data in result.values():
                    if isinstance(pair_data, dict) and 'c' in pair_data:
                        return float(pair_data['c'][0])  # 最新价格
            
            elif 'gemini.com' in api_url:
                return float(data.get('last', 0))
            
            elif 'bitstamp.net' in api_url:
                return float(data.get('last', 0))
            
            elif 'okx.com' in api_url:
                arr = data.get('data', [])
                if isinstance(arr, list) and arr:
                    return float(arr[0].get('last', 0))
            
            elif 'bybit.com' in api_url:
                result = data.get('result', {})
                lst = result.get('list', []) if isinstance(result, dict) else []
                if isinstance(lst, list) and lst:
                    return float(lst[0].get('lastPrice', 0))
            
            elif 'gateio.ws' in api_url:
                if isinstance(data, list) and data:
                    return float(data[0].get('last', 0))
            
            elif 'kucoin.com' in api_url:
                d = data.get('data', {})
                if isinstance(d, dict):
                    return float(d.get('last', 0))
            
            elif 'bitfinex.com' in api_url:
                # 兼容 v1 和 v2
                # v1: /v1/pubticker/{symbol} -> { last_price: "..." }
                if isinstance(data, dict) and 'last_price' in data:
                    return float(data.get('last_price', 0))
                # v2: /v2/ticker/tBTCUSD -> [BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE, DAILY_CHANGE_PERC, LAST_PRICE, ...]
                # v2: /v2/tickers?symbols=tBTCUSD -> [["tBTCUSD", BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE, DAILY_CHANGE_PERC, LAST_PRICE, ...]]
                if isinstance(data, list) and data:
                    first = data[0]
                    # /v2/ticker 返回的是数值数组
                    if isinstance(first, (int, float)):
                        return float(data[6])  # LAST_PRICE 索引 6
                    # /v2/tickers 返回的是数组的数组，第一项是符号字符串
                    if isinstance(first, list) and len(first) > 8:
                        return float(first[7])  # LAST_PRICE 索引 7
            
            elif 'coingecko.com' in api_url:
                # simple/price 返回 { coin_id: { usd: number } }
                if isinstance(data, dict) and data:
                    coin_obj = next(iter(data.values()))
                    if isinstance(coin_obj, dict):
                        # 优先 usd / USD
                        val = coin_obj.get('usd', coin_obj.get('USD', 0))
                        return float(val)
            
            elif 'cryptocompare.com' in api_url:
                # { "USD": number }
                val = data.get('USD') if isinstance(data, dict) else None
                if val is not None:
                    return float(val)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            self.logger.warning(f"价格解析失败 {api_url}: {e}")
        
        return None
    
    def _should_skip_api(self, api_url: str) -> bool:
        """检查是否应该跳过某个API"""
        failure_count = self.failure_counts.get(api_url, 0)
        last_failure = self.last_failure_time.get(api_url, 0)
        
        # 如果失败次数过多且最近失败过，则跳过
        if failure_count >= 3:
            time_since_failure = time.time() - last_failure
            if time_since_failure < 300:  # 5分钟内跳过
                return True
                
        return False
    
    def _record_failure(self, api_url: str):
        """记录API失败"""
        self.failure_counts[api_url] = self.failure_counts.get(api_url, 0) + 1
        self.last_failure_time[api_url] = time.time()
    
    def _record_success(self, api_url: str):
        """记录API成功"""
        # 成功后重置失败计数
        if api_url in self.failure_counts:
            self.failure_counts[api_url] = 0


# 全局实例
_fallback_manager: Optional[APIFallbackManager] = None


def get_fallback_manager() -> APIFallbackManager:
    """获取全局备用API管理器"""
    global _fallback_manager
    if _fallback_manager is None:
        _fallback_manager = APIFallbackManager()
    return _fallback_manager


if __name__ == "__main__":
    # 测试备用API管理器
    manager = APIFallbackManager()
    
    symbols = ['bitcoin', 'ethereum', 'cardano', 'ripple']
    
    for symbol in symbols:
        print(f"测试 {symbol} 价格获取...")
        price, latency, error, ts, headers = manager.get_price_with_fallback(symbol)
        print(f"  结果: price={price}, latency={latency:.2f}ms, error={error}")
        time.sleep(1)  # 避免请求过于频繁
