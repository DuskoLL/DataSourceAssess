#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HTTP 客户端模块
提供统一的HTTP请求接口，支持重试、超时、并发控制
"""

import time
import json
import threading
import gzip
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Callable, Any
from urllib import request, error
from email.utils import parsedate_to_datetime

from logger import get_logger
from config_loader import get_config


class HTTPClient:
    """HTTP客户端"""
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config or get_config()
        self.logger = get_logger("http_client", self.config)
        self.executor = ThreadPoolExecutor(max_workers=self.config.network.concurrent_requests)
        self._request_count = 0
        self._lock = threading.Lock()
    
    def _headers_to_dict(self, hdrs) -> Dict[str, str]:
        """转换响应头为字典"""
        try:
            return {k: v for k, v in hdrs.items()}
        except Exception:
            return {}
    
    def _get_with_retry(self, url: str, timeout_sec: float, retries: int) -> Tuple[Optional[dict], float, Optional[str], Dict[str, str]]:
        """带重试的HTTP GET请求"""
        last_error = None
        
        for attempt in range(retries + 1):
            start_time = time.time()
            
            try:
                req = request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; oracle-lab/2.0; +https://example.org)",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                    "Connection": "close",  # 避免连接池问题
                    "DNT": "1",
                    "Pragma": "no-cache"
                })
                
                with request.urlopen(req, timeout=timeout_sec) as resp:
                    raw = resp.read()
                    latency_ms = (time.time() - start_time) * 1000.0
                    headers = self._headers_to_dict(resp.headers)
                    
                    try:
                        # 检查是否为gzip压缩的内容
                        content_encoding = headers.get('content-encoding', '').lower()
                        if content_encoding == 'gzip' or (raw.startswith(b'\x1f\x8b')):
                            # 解压gzip内容
                            try:
                                raw = gzip.decompress(raw)
                                self.logger.debug(f"已解压gzip内容: {url}")
                            except Exception as decomp_err:
                                error_msg = f"gzip_decompress_error: {decomp_err}"
                                self.logger.warning(f"gzip解压失败: {url} - {error_msg}")
                                return None, latency_ms, error_msg, headers
                        
                        # 尝试解码文本
                        try:
                            text_content = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            try:
                                text_content = raw.decode("latin-1")
                                self.logger.debug(f"使用latin-1编码解码: {url}")
                            except Exception as decode_err:
                                error_msg = f"text_decode_error: {decode_err}"
                                self.logger.warning(f"文本解码失败: {url} - {error_msg}")
                                return None, latency_ms, error_msg, headers
                        
                        # 解析JSON
                        data = json.loads(text_content)
                        self.logger.debug(f"HTTP请求成功: {url} ({latency_ms:.2f}ms)")
                        return data, latency_ms, None, headers
                        
                    except json.JSONDecodeError as je:
                        error_msg = f"json_decode_error: {je}"
                        self.logger.warning(f"JSON解析失败: {url} - {error_msg}")
                        return None, latency_ms, error_msg, headers
                        
            except error.HTTPError as he:
                latency_ms = (time.time() - start_time) * 1000.0
                last_error = f"http_error: {he.code}"
                if attempt < retries:
                    self.logger.warning(f"HTTP错误 {he.code}，重试 {attempt + 1}/{retries}: {url}")
                    time.sleep(0.5 * (attempt + 1))  # 递增延迟
                    continue
                    
            except error.URLError as ue:
                latency_ms = (time.time() - start_time) * 1000.0
                last_error = f"url_error: {ue.reason}"
                if attempt < retries:
                    self.logger.warning(f"URL错误，重试 {attempt + 1}/{retries}: {url} - {ue.reason}")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                    
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000.0
                last_error = f"error: {e}"
                if attempt < retries:
                    self.logger.warning(f"请求异常，重试 {attempt + 1}/{retries}: {url} - {e}")
                    time.sleep(0.5 * (attempt + 1))
                    continue
        
        # 所有重试都失败了
        self.logger.error(f"HTTP请求最终失败: {url} - {last_error}")
        return None, latency_ms, last_error, {}
    
    def get_json(self, url: str, timeout_sec: Optional[float] = None) -> Tuple[Optional[dict], float, Optional[str], Dict[str, str]]:
        """GET请求并解析JSON"""
        with self._lock:
            self._request_count += 1
            request_id = self._request_count
        
        timeout = timeout_sec or self.config.network.timeout_sec
        retries = self.config.network.retries
        
        self.logger.debug(f"发起HTTP请求[{request_id}]: {url}")
        
        from logger import LoggerContext
        with LoggerContext(self.logger, "http_request"):
            result = self._get_with_retry(url, timeout, retries)
        
        self.logger.record_event("http_requests_total")
        if result[2] is None:  # 无错误
            self.logger.record_event("http_requests_success")
        else:
            self.logger.record_event("http_requests_failed")
        
        return result
    
    def get_json_batch(self, urls: List[str], timeout_sec: Optional[float] = None) -> List[Tuple[str, Optional[dict], float, Optional[str], Dict[str, str]]]:
        """批量并发GET请求"""
        timeout = timeout_sec or self.config.network.timeout_sec
        
        self.logger.info(f"开始批量HTTP请求: {len(urls)} 个URL")
        
        futures = {}
        with self.executor:
            for url in urls:
                future = self.executor.submit(self.get_json, url, timeout)
                futures[future] = url
            
            results = []
            for future in as_completed(futures):
                url = futures[future]
                try:
                    data, latency, error, headers = future.result()
                    results.append((url, data, latency, error, headers))
                except Exception as e:
                    self.logger.error(f"批量请求异常: {url} - {e}")
                    results.append((url, None, 0.0, f"future_error: {e}", {}))
        
        self.logger.info(f"批量HTTP请求完成: {len(results)} 个结果")
        return results
    
    def close(self):
        """关闭HTTP客户端"""
        self.executor.shutdown(wait=True)


# 全局HTTP客户端实例
_http_client: Optional[HTTPClient] = None
_client_lock = threading.Lock()


def get_http_client() -> HTTPClient:
    """获取全局HTTP客户端实例"""
    global _http_client
    with _client_lock:
        if _http_client is None:
            _http_client = HTTPClient()
        return _http_client


def http_get_json(url: str, timeout_sec: float = 5.0) -> Tuple[Optional[dict], float, Optional[str], Dict[str, str]]:
    """便捷的HTTP GET JSON方法（向后兼容）"""
    client = get_http_client()
    return client.get_json(url, timeout_sec)


if __name__ == "__main__":
    # 测试HTTP客户端
    from config_loader import load_config
    
    config = load_config()
    client = HTTPClient(config)
    
    # 测试单个请求
    print("测试单个请求...")
    data, latency, error, headers = client.get_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    print(f"结果: data={data}, latency={latency:.2f}ms, error={error}")
    
    # 测试批量请求
    print("\n测试批量请求...")
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
        "https://api.coinbase.com/v2/exchange-rates?currency=BTC"
    ]
    
    batch_results = client.get_json_batch(urls)
    for url, data, latency, error, headers in batch_results:
        print(f"URL: {url}")
        print(f"  结果: latency={latency:.2f}ms, error={error}")
        print(f"  数据: {data is not None}")
    
    # 打印性能统计
    stats = client.logger.get_performance_stats()
    print(f"\n性能统计: {stats}")
    
    client.close()
