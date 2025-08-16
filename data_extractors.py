#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据提取器模块
包含各种数据源API的数据提取逻辑
"""

import time
from typing import Dict, List, Optional, Tuple, Callable
from email.utils import parsedate_to_datetime

from http_client import get_http_client
from logger import get_logger
from config_loader import get_config
from api_fallback_manager import get_fallback_manager


class DataExtractor:
    """数据提取器基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.config = get_config()
        self.logger = get_logger(f"extractor_{name}", self.config)
        self.http_client = get_http_client()
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        """提取数据，返回 (value, latency_ms, error, server_ts_ms, headers)"""
        raise NotImplementedError
    
    def _parse_iso8601_utc_millis(self, val: str) -> Optional[float]:
        """解析ISO8601时间戳为UTC毫秒"""
        try:
            dt = parsedate_to_datetime(val)
            return dt.timestamp() * 1000.0
        except Exception:
            return None


class FallbackExtractor(DataExtractor):
    """使用备用API的数据提取器"""
    
    def __init__(self):
        super().__init__("fallback")
        self.fallback_manager = get_fallback_manager()
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        """使用备用API策略提取数据"""
        # 从URL中推断要获取的加密货币类型
        symbol = self._infer_symbol_from_url(url)
        
        if symbol:
            # 使用备用API管理器
            return self.fallback_manager.get_price_with_fallback(symbol)
        else:
            # 如果无法推断符号，尝试原始URL
            data, latency, err, headers = self.http_client.get_json(url)
            if err:
                return None, latency, f"fallback:{err}", None, headers
            
            # 尝试从响应中提取价格
            price = self._extract_price_generic(data)
            server_ts = time.time() * 1000.0
            
            return price, latency, None if price else "price_not_found", server_ts, headers
    
    def _infer_symbol_from_url(self, url: str) -> Optional[str]:
        """从URL推断加密货币符号"""
        url_lower = url.lower()
        
        if 'btc' in url_lower or 'bitcoin' in url_lower:
            return 'bitcoin'
        elif 'eth' in url_lower or 'ethereum' in url_lower:
            return 'ethereum'
        elif 'ada' in url_lower or 'cardano' in url_lower:
            return 'cardano'
        elif 'xrp' in url_lower or 'ripple' in url_lower:
            return 'ripple'
        elif 'doge' in url_lower or 'dogecoin' in url_lower:
            return 'dogecoin'
        elif 'sol' in url_lower or 'solana' in url_lower:
            return 'solana'
        elif 'trx' in url_lower or 'tron' in url_lower:
            return 'tron'
        elif 'dot' in url_lower or 'polkadot' in url_lower:
            return 'polkadot'
        
        return None
    
    def _extract_price_generic(self, data: Dict) -> Optional[float]:
        """通用价格提取方法"""
        if not data:
            return None
        
        # 尝试常见的价格字段
        price_fields = ['price', 'last', 'last_price', 'close', 'rate', 'value']
        
        for field in price_fields:
            if field in data:
                try:
                    return float(data[field])
                except (ValueError, TypeError):
                    continue
        
        # 检查嵌套结构
        if 'data' in data:
            return self._extract_price_generic(data['data'])
        
        if 'result' in data:
            return self._extract_price_generic(data['result'])
        
        return None


class BinanceExtractor(DataExtractor):
    """Binance交易所数据提取器"""
    
    def __init__(self):
        super().__init__("binance")
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"binance:{err}", None, headers
        
        try:
            price = float(data["price"])  # type: ignore
            return price, latency, None, None, headers
        except Exception as e:
            return None, latency, f"binance_parse:{e}", None, headers


class CoinbaseExtractor(DataExtractor):
    """Coinbase交易所数据提取器"""
    
    def __init__(self):
        super().__init__("coinbase")
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"coinbase:{err}", None, headers
        
        try:
            price = float(data["price"])  # type: ignore
            
            # 尝试解析服务器时间戳
            server_ts = None
            timestamp = data.get("time")  # type: ignore
            if isinstance(timestamp, str):
                server_ts = self._parse_iso8601_utc_millis(timestamp)
            
            return price, latency, None, server_ts, headers
        except Exception as e:
            return None, latency, f"coinbase_parse:{e}", None, headers


class KrakenExtractor(DataExtractor):
    """Kraken交易所数据提取器"""
    
    def __init__(self):
        super().__init__("kraken")
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"kraken:{err}", None, headers
        
        try:
            result = data.get("result", {})  # type: ignore
            if not result:
                return None, latency, "kraken_parse:empty_result", None, headers
            
            # Kraken返回的键可能变化，取第一个
            pair_data = next(iter(result.values()))
            price = float(pair_data["c"][0])  # 最新收盘价
            
            return price, latency, None, None, headers
        except Exception as e:
            return None, latency, f"kraken_parse:{e}", None, headers


class BitstampExtractor(DataExtractor):
    """Bitstamp交易所数据提取器"""
    
    def __init__(self):
        super().__init__("bitstamp")
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"bitstamp:{err}", None, headers
        
        try:
            price = float(data["last"])  # type: ignore
            
            # 尝试解析时间戳
            server_ts = None
            timestamp = data.get("timestamp")  # type: ignore
            if isinstance(timestamp, str) and timestamp.isdigit():
                server_ts = float(timestamp) * 1000.0  # 转换为毫秒
            
            return price, latency, None, server_ts, headers
        except Exception as e:
            return None, latency, f"bitstamp_parse:{e}", None, headers


class OKXExtractor(DataExtractor):
    """OKX交易所数据提取器"""
    
    def __init__(self):
        super().__init__("okx")
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"okx:{err}", None, headers
        
        try:
            arr = data.get("data", [])  # type: ignore
            if not arr:
                return None, latency, "okx_parse:empty", None, headers
            
            price = float(arr[0]["last"])  # type: ignore
            
            # 尝试解析时间戳
            server_ts = None
            ts = arr[0].get("ts")  # type: ignore
            if isinstance(ts, str) and ts.isdigit():
                server_ts = float(ts)
            
            return price, latency, None, server_ts, headers
        except Exception as e:
            return None, latency, f"okx_parse:{e}", None, headers


class GenericJSONExtractor(DataExtractor):
    """通用JSON数据提取器"""
    
    def __init__(self, category: str):
        super().__init__(f"generic_{category}")
        self.category = category
    
    def extract_value_from_json(self, obj: dict, category: str) -> Optional[float]:
        """从JSON对象中提取特定类别的数值"""
        # 允许顶层为列表的情况（如 Gate.io 返回数组）
        if isinstance(obj, list) and obj:
            first_item = obj[0]
            if isinstance(first_item, dict):
                for field in ["price", "last", "close", "usd", "USD", "value", "result"]:
                    if field in first_item:
                        try:
                            return float(first_item[field])
                        except (ValueError, TypeError):
                            pass
            return None
        
        if not isinstance(obj, dict):
            return None
        
        # 定义各类别的常见字段名
        field_mappings = {
            "bitcoin_price": ["price", "last", "close", "usd", "USD"],
            "ethereum_price": ["price", "last", "close", "usd", "USD"],
            "tether_price": ["price", "last", "close", "usd", "USD"],
            "bnb_price": ["price", "last", "close", "usd", "USD"],
            "xrp_price": ["price", "last", "close", "usd", "USD"],
            "cardano_price": ["price", "last", "close", "usd", "USD"],
            "dogecoin_price": ["price", "last", "close", "usd", "USD"],
            "solana_price": ["price", "last", "close", "usd", "USD"],
            "tron_price": ["price", "last", "close", "usd", "USD"],
            "polkadot_price": ["price", "last", "close", "usd", "USD"],
            "avalanche_price": ["price", "last", "close", "usd", "USD"],
            "avax_price": ["price", "last", "close", "usd", "USD"],
        }
        
        # 默认也包含常见价格字段
        possible_fields = field_mappings.get(category, ["price", "last", "close", "usd", "USD", "value", "result"])
        
        # 尝试直接字段匹配
        for field in possible_fields:
            if isinstance(obj.get(field), (int, float, str)):
                try:
                    return float(obj[field])
                except (ValueError, TypeError):
                    continue
        
        # 尝试嵌套结构（对象内的常见容器）
        for container in ["data", "result", "ticker", "stats"]:
            sub = obj.get(container)
            if isinstance(sub, dict):
                for field in possible_fields:
                    if isinstance(sub.get(field), (int, float, str)):
                        try:
                            return float(sub[field])
                        except (ValueError, TypeError):
                            continue
            
            # 尝试数组结构（容器为数组）
            if isinstance(sub, list) and sub:
                first_item = sub[0]
                if isinstance(first_item, dict):
                    for field in possible_fields:
                        if isinstance(first_item.get(field), (int, float, str)):
                            try:
                                return float(first_item[field])
                            except (ValueError, TypeError):
                                continue
        
        return None
    
    def extract(self, url: str) -> Tuple[Optional[float], float, Optional[str], Optional[float], Dict[str, str]]:
        data, latency, err, headers = self.http_client.get_json(url)
        if err:
            return None, latency, f"generic:{err}", None, headers
        
        try:
            value = self.extract_value_from_json(data, self.category)  # type: ignore
            if value is None:
                return None, latency, "generic_parse:no_value_found", None, headers
            
            return value, latency, None, None, headers
        except Exception as e:
            return None, latency, f"generic_parse:{e}", None, headers


# 数据提取器注册表
_extractors: Dict[str, DataExtractor] = {}


def register_extractor(name: str, extractor: DataExtractor):
    """注册数据提取器"""
    _extractors[name] = extractor


def get_extractor(name: str) -> Optional[DataExtractor]:
    """获取数据提取器"""
    return _extractors.get(name)


def get_extractor_for_category(category: str) -> DataExtractor:
    """为特定类别获取最佳提取器（优先使用备用API）"""
    # 对于加密货币价格类别，优先使用备用提取器
    crypto_categories = [
        "bitcoin_price", "ethereum_price", "cardano_price", "xrp_price",
        "dogecoin_price", "solana_price", "tron_price", "polkadot_price",
        "bnb_price", "avalanche_price", "avax_price", "tether_price"
    ]
    
    if category in crypto_categories:
        fallback_name = f"fallback_{category}"
        if fallback_name not in _extractors:
            _extractors[fallback_name] = FallbackExtractor()
        return _extractors[fallback_name]
    
    # 其他类别使用通用提取器
    extractor_name = f"generic_{category}"
    if extractor_name not in _extractors:
        _extractors[extractor_name] = GenericJSONExtractor(category)
    return _extractors[extractor_name]


# 注册内置提取器
register_extractor("binance", BinanceExtractor())
register_extractor("coinbase", CoinbaseExtractor())
register_extractor("kraken", KrakenExtractor())
register_extractor("bitstamp", BitstampExtractor())
register_extractor("okx", OKXExtractor())


# 向后兼容的函数
def extract_value_from_json(obj: dict, category: str) -> Optional[float]:
    """提取JSON值（向后兼容）"""
    extractor = get_extractor_for_category(category)
    return extractor.extract_value_from_json(obj, category)


if __name__ == "__main__":
    # 测试数据提取器
    print("测试数据提取器...")
    
    # 测试Binance
    binance = get_extractor("binance")
    if binance:
        result = binance.extract("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
        print(f"Binance结果: value={result[0]}, latency={result[1]:.2f}ms, error={result[2]}")
    
    # 测试通用提取器
    generic = get_extractor_for_category("bitcoin_price")
    test_data = {"price": "45000.50", "timestamp": "2024-01-01T12:00:00Z"}
    value = generic.extract_value_from_json(test_data, "bitcoin_price")
    print(f"通用提取器结果: {value}")
