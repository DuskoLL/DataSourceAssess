#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一日志系统
支持文件和控制台输出，日志轮转，性能监控
"""

import os
import sys
import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime
from collections import defaultdict, deque


class LogLevel:
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class PerformanceTracker:
    """性能监控追踪器"""
    
    def __init__(self):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.counters: Dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()
    
    def record_timing(self, operation: str, duration_ms: float):
        """记录操作耗时"""
        with self.lock:
            self.metrics[f"{operation}_timing"].append(duration_ms)
            self.counters[f"{operation}_count"] += 1
    
    def record_event(self, event: str, value: float = 1.0):
        """记录事件"""
        with self.lock:
            self.metrics[event].append(value)
            self.counters[f"{event}_count"] += 1
    
    def get_stats(self, operation: str) -> Dict[str, Any]:
        """获取操作统计信息"""
        with self.lock:
            timings = list(self.metrics.get(f"{operation}_timing", []))
            if not timings:
                return {}
            
            return {
                "count": len(timings),
                "avg_ms": sum(timings) / len(timings),
                "min_ms": min(timings),
                "max_ms": max(timings),
                "total_count": self.counters.get(f"{operation}_count", 0)
            }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有统计信息"""
        stats = {}
        with self.lock:
            operations = set()
            for key in self.metrics.keys():
                if key.endswith("_timing"):
                    operations.add(key[:-7])  # 移除"_timing"后缀
            
            for op in operations:
                stats[op] = self.get_stats(op)
            
            # 添加计数器信息
            stats["counters"] = dict(self.counters)
        
        return stats


class Logger:
    """统一日志记录器"""
    
    def __init__(self, name: str, config: Optional[Any] = None):
        self.name = name
        self.config = config
        self.level = getattr(LogLevel, config.logging.level if config else "INFO", LogLevel.INFO)
        self.lock = threading.Lock()
        self.performance = PerformanceTracker()
        
        # 确保日志目录存在
        if config and config.logging.file_enabled:
            log_dir = os.path.dirname(config.logging.file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
    
    def _format_message(self, level: str, message: str) -> str:
        """格式化日志消息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{timestamp} - {self.name} - {level} - {message}"
    
    def _write_to_file(self, formatted_message: str):
        """写入日志文件"""
        if not (self.config and self.config.logging.file_enabled):
            return
        
        try:
            # 简单的日志轮转检查
            log_path = self.config.logging.file_path
            if os.path.exists(log_path):
                size_mb = os.path.getsize(log_path) / (1024 * 1024)
                if size_mb > self.config.logging.max_file_size_mb:
                    # 备份当前日志文件
                    backup_path = f"{log_path}.{int(time.time())}"
                    os.rename(log_path, backup_path)
                    
                    # 清理旧备份（简单实现）
                    log_dir = os.path.dirname(log_path)
                    log_name = os.path.basename(log_path)
                    backups = [f for f in os.listdir(log_dir) if f.startswith(log_name + ".")]
                    backups.sort()
                    while len(backups) > self.config.logging.backup_count:
                        os.remove(os.path.join(log_dir, backups.pop(0)))
            
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(formatted_message + '\n')
                f.flush()
        except Exception as e:
            # 避免日志系统本身出错导致程序崩溃
            print(f"日志写入错误: {e}", file=sys.stderr)
    
    def _write_to_console(self, formatted_message: str):
        """写入控制台"""
        if self.config and self.config.logging.console_enabled:
            print(formatted_message)
    
    def _log(self, level: int, level_name: str, message: str):
        """内部日志方法"""
        if level < self.level:
            return
        
        with self.lock:
            formatted = self._format_message(level_name, message)
            self._write_to_console(formatted)
            self._write_to_file(formatted)
    
    def debug(self, message: str):
        """调试日志"""
        self._log(LogLevel.DEBUG, "DEBUG", message)
    
    def info(self, message: str):
        """信息日志"""
        self._log(LogLevel.INFO, "INFO", message)
    
    def warning(self, message: str):
        """警告日志"""
        self._log(LogLevel.WARNING, "WARNING", message)
    
    def error(self, message: str):
        """错误日志"""
        self._log(LogLevel.ERROR, "ERROR", message)
    
    def critical(self, message: str):
        """严重错误日志"""
        self._log(LogLevel.CRITICAL, "CRITICAL", message)
    
    def time_operation(self, operation_name: str):
        """操作计时装饰器"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.time() - start_time) * 1000
                    self.performance.record_timing(operation_name, duration_ms)
                    self.debug(f"{operation_name} 耗时: {duration_ms:.2f}ms")
            return wrapper
        return decorator
    
    def record_event(self, event: str, value: float = 1.0):
        """记录事件"""
        self.performance.record_event(event, value)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return self.performance.get_all_stats()


# 全局日志管理器
_loggers: Dict[str, Logger] = {}
_lock = threading.Lock()


def get_logger(name: str, config: Optional[Any] = None) -> Logger:
    """获取日志记录器实例"""
    with _lock:
        if name not in _loggers:
            _loggers[name] = Logger(name, config)
        return _loggers[name]


def setup_logging(config: Any):
    """设置全局日志配置"""
    # 清空现有日志器并重新配置
    with _lock:
        _loggers.clear()


class LoggerContext:
    """日志上下文管理器，用于性能监控"""
    
    def __init__(self, logger: Logger, operation: str):
        self.logger = logger
        self.operation = operation
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.logger.performance.record_timing(self.operation, duration_ms)
            if exc_type:
                self.logger.error(f"{self.operation} 失败: {exc_val}")
            else:
                self.logger.debug(f"{self.operation} 完成，耗时: {duration_ms:.2f}ms")


if __name__ == "__main__":
    # 测试日志系统
    from config_loader import load_config
    
    config = load_config()
    logger = get_logger("test", config)
    
    logger.info("日志系统测试开始")
    logger.debug("这是调试信息")
    logger.warning("这是警告信息")
    logger.error("这是错误信息")
    
    # 测试性能监控
    with LoggerContext(logger, "test_operation"):
        time.sleep(0.1)
    
    # 测试装饰器
    @logger.time_operation("decorated_function")
    def test_func():
        time.sleep(0.05)
        return "测试完成"
    
    result = test_func()
    logger.info(f"函数结果: {result}")
    
    # 打印性能统计
    stats = logger.get_performance_stats()
    logger.info(f"性能统计: {stats}")
