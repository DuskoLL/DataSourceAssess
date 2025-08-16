# 模块化重构迁移指南

## 重构概览

系统已重构为模块化架构，包含以下新模块：

### 新模块结构
- `config_loader.py` - 配置管理
- `logger.py` - 统一日志系统
- `http_client.py` - HTTP客户端（支持重试、并发）
- `data_extractors.py` - 数据提取器
- `clustering.py` - 优化的聚类算法
- `storage.py` - 存储层（支持文件锁、备份）
- `oracle_chain.py` - 重构后的核心模块

### 配置文件
- `config.yaml` - 主配置文件，包含所有可调参数

### 主要改进
1. **性能优化**
   - K-means聚类缓存
   - 并发HTTP请求支持
   - 文件操作优化

2. **可维护性**
   - 模块化设计
   - 统一错误处理
   - 完整的日志系统

3. **可配置性**
   - YAML配置文件
   - 环境变量覆盖
   - 运行时参数调整

### 向后兼容性
原有的API接口保持不变，现有代码无需修改即可运行。

### 运行方式
```bash
# 使用配置文件运行
python3 proposer_node.py --id proposer-1
python3 miner_node.py --id miner-1 --quorum 3

# 环境变量覆盖配置
ORACLE_NETWORK_TIMEOUT_SEC=10 python3 proposer_node.py --id proposer-1
```

### 监控和调试
- 日志文件：`logs/oracle.log`
- 性能指标：通过日志系统API获取
- 配置验证：运行 `python3 config_loader.py`

### 故障恢复
如遇问题，可使用备份文件恢复：
- `oracle_chain_original.py` - 原始核心文件
- `*.backup` - 节点文件备份
