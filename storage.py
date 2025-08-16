#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
存储层模块
提供统一的数据持久化接口，支持文件锁和备份
"""

import os
import json
import time
import threading
import shutil
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from logger import get_logger
from config_loader import get_config


class FileStorage:
    """文件存储管理器"""
    
    def __init__(self, config: Optional[Any] = None):
        self.config = config or get_config()
        self.logger = get_logger("storage", self.config)
        self.base_dir = self.config.storage.state_dir
        self.backup_enabled = self.config.storage.backup_enabled
        self.backup_interval = self.config.storage.backup_interval_sec
        self.locks: Dict[str, threading.Lock] = {}
        self.lock_manager = threading.Lock()
        self.last_backup = {}
        
        self.ensure_directories()
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        dirs_to_create = [
            self.base_dir,
            os.path.join(self.base_dir, "proposals"),
            os.path.join(self.base_dir, "backups") if self.backup_enabled else None
        ]
        
        for dir_path in dirs_to_create:
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                self.logger.debug(f"创建目录: {dir_path}")
    
    def _get_file_lock(self, file_path: str) -> threading.Lock:
        """获取文件专用锁"""
        with self.lock_manager:
            if file_path not in self.locks:
                self.locks[file_path] = threading.Lock()
            return self.locks[file_path]
    
    @contextmanager
    def _file_lock(self, file_path: str):
        """文件锁上下文管理器"""
        lock = self._get_file_lock(file_path)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
    
    def _create_backup(self, file_path: str):
        """创建文件备份"""
        if not self.backup_enabled or not os.path.exists(file_path):
            return
        
        current_time = time.time()
        last_backup_time = self.last_backup.get(file_path, 0)
        
        if current_time - last_backup_time < self.backup_interval:
            return
        
        try:
            backup_dir = os.path.join(self.base_dir, "backups")
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)
            
            file_name = os.path.basename(file_path)
            backup_name = f"{file_name}.{int(current_time)}.bak"
            backup_path = os.path.join(backup_dir, backup_name)
            
            shutil.copy2(file_path, backup_path)
            self.last_backup[file_path] = current_time
            self.logger.debug(f"创建备份: {backup_path}")
            
            # 清理旧备份
            self._cleanup_old_backups(backup_dir, file_name)
            
        except Exception as e:
            self.logger.warning(f"创建备份失败 {file_path}: {e}")
    
    def _cleanup_old_backups(self, backup_dir: str, file_name: str, keep_count: int = 5):
        """清理旧备份文件"""
        try:
            backup_files = [
                f for f in os.listdir(backup_dir)
                if f.startswith(file_name + ".") and f.endswith(".bak")
            ]
            
            # 按时间戳排序
            backup_files.sort(key=lambda x: int(x.split('.')[-2]))
            
            # 删除多余的备份
            while len(backup_files) > keep_count:
                old_backup = backup_files.pop(0)
                old_backup_path = os.path.join(backup_dir, old_backup)
                os.remove(old_backup_path)
                self.logger.debug(f"删除旧备份: {old_backup_path}")
                
        except Exception as e:
            self.logger.warning(f"清理备份失败: {e}")
    
    def load_json(self, file_path: str, default: Any = None) -> Any:
        """加载JSON文件"""
        full_path = self._get_full_path(file_path)
        
        with self._file_lock(full_path):
            from logger import LoggerContext
            with LoggerContext(self.logger, f"load_json_{os.path.basename(file_path)}"):
                try:
                    if not os.path.exists(full_path):
                        return default
                    
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if not content.strip():
                            return default
                        
                        data = json.loads(content)
                        self.logger.debug(f"加载JSON文件: {full_path}")
                        return data
                        
                except json.JSONDecodeError as e:
                    self.logger.error(f"JSON解析错误 {full_path}: {e}")
                    return default
                except Exception as e:
                    self.logger.error(f"加载文件失败 {full_path}: {e}")
                    return default
    
    def save_json(self, file_path: str, data: Any, create_backup: bool = True):
        """保存JSON文件"""
        full_path = self._get_full_path(file_path)
        
        with self._file_lock(full_path):
            from logger import LoggerContext
            with LoggerContext(self.logger, f"save_json_{os.path.basename(file_path)}"):
                try:
                    # 创建备份
                    if create_backup:
                        self._create_backup(full_path)
                    
                    # 确保目录存在
                    dir_path = os.path.dirname(full_path)
                    if not os.path.exists(dir_path):
                        os.makedirs(dir_path, exist_ok=True)
                    
                    # 原子写入（先写临时文件，再重命名）
                    temp_path = full_path + ".tmp"
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())  # 强制写入磁盘
                    
                    # 原子重命名
                    if os.path.exists(full_path):
                        if os.name == 'nt':  # Windows
                            os.remove(full_path)
                    os.rename(temp_path, full_path)
                    
                    self.logger.debug(f"保存JSON文件: {full_path}")
                    
                except Exception as e:
                    self.logger.error(f"保存文件失败 {full_path}: {e}")
                    # 清理临时文件
                    temp_path = full_path + ".tmp"
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    raise
    
    def delete_file(self, file_path: str):
        """删除文件"""
        full_path = self._get_full_path(file_path)
        
        with self._file_lock(full_path):
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    self.logger.debug(f"删除文件: {full_path}")
            except Exception as e:
                self.logger.error(f"删除文件失败 {full_path}: {e}")
                raise
    
    def list_files(self, dir_path: str, pattern: Optional[str] = None) -> List[str]:
        """列出目录中的文件"""
        full_dir = self._get_full_path(dir_path)
        
        try:
            if not os.path.exists(full_dir):
                return []
            
            files = os.listdir(full_dir)
            
            if pattern:
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f, pattern)]
            
            return files
            
        except Exception as e:
            self.logger.error(f"列出文件失败 {full_dir}: {e}")
            return []
    
    def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        full_path = self._get_full_path(file_path)
        return os.path.exists(full_path)
    
    def get_file_size(self, file_path: str) -> int:
        """获取文件大小"""
        full_path = self._get_full_path(file_path)
        try:
            return os.path.getsize(full_path)
        except:
            return 0
    
    def get_file_mtime(self, file_path: str) -> float:
        """获取文件修改时间"""
        full_path = self._get_full_path(file_path)
        try:
            return os.path.getmtime(full_path)
        except:
            return 0.0
    
    def _get_full_path(self, file_path: str) -> str:
        """获取完整路径"""
        if os.path.isabs(file_path):
            return file_path
        return os.path.join(self.base_dir, file_path)


# 全局存储实例
_storage: Optional[FileStorage] = None
_storage_lock = threading.Lock()


def get_storage() -> FileStorage:
    """获取全局存储实例"""
    global _storage
    with _storage_lock:
        if _storage is None:
            _storage = FileStorage()
        return _storage


# 向后兼容的函数
def load_json_file(file_path: str, default: Any = None) -> Any:
    """加载JSON文件（向后兼容）"""
    storage = get_storage()
    return storage.load_json(file_path, default)


def save_json_file(file_path: str, data: Any):
    """保存JSON文件（向后兼容）"""
    storage = get_storage()
    storage.save_json(file_path, data)


def ensure_dirs():
    """确保目录存在（向后兼容）"""
    storage = get_storage()
    storage.ensure_directories()


if __name__ == "__main__":
    # 测试存储系统
    from config_loader import load_config
    
    config = load_config()
    storage = FileStorage(config)
    
    # 测试JSON读写
    print("测试存储系统...")
    
    test_data = {
        "test": "data",
        "timestamp": time.time(),
        "items": [1, 2, 3, 4, 5]
    }
    
    # 保存测试数据
    storage.save_json("test.json", test_data)
    print("保存测试数据完成")
    
    # 读取测试数据
    loaded_data = storage.load_json("test.json")
    print(f"读取测试数据: {loaded_data == test_data}")
    
    # 测试文件信息
    file_size = storage.get_file_size("test.json")
    file_mtime = storage.get_file_mtime("test.json")
    print(f"文件大小: {file_size} 字节")
    print(f"修改时间: {time.ctime(file_mtime)}")
    
    # 清理测试文件
    storage.delete_file("test.json")
    print("清理测试文件完成")
