# 预言机数据源评估区块链系统（重构版本）

本系统是一个模块化的预言机数据源评估区块链实验平台，采用分布式架构评估和管理数据源API的可信度。

## 🏗️ 系统架构

### 模块化设计
- **`oracle_chain.py`** - 核心业务逻辑（重构版本）
- **`config_loader.py`** - 配置管理系统
- **`logger.py`** - 统一日志系统
- **`http_client.py`** - HTTP客户端（支持重试、并发）
- **`data_extractors.py`** - 数据提取器
- **`clustering.py`** - 优化的聚类算法
- **`storage.py`** - 存储层（支持文件锁、备份）
- **`proposer_node.py`** - 提案节点
- **`miner_node.py`** - 矿工节点
- **`generate_virtual_sources.py`** - 虚拟数据源生成器

### 节点角色
- **提案节点（Proposer）**: 评估数据源并投票，支持动态添加新数据源
- **矿工节点（Miner）**: 聚合投票、达成共识、出块、周期性聚类维护

### 数据类型
支持十类加密货币价格数据源：
- Bitcoin、Ethereum、Tether、BNB、XRP
- Cardano、Dogecoin、Solana、Tron、Polkadot

## 🚀 环境准备

### 系统要求
- Python 3.9+
- 仅依赖标准库（无需额外安装包）

### 目录结构
```
code/
├── config.yaml              # 主配置文件
├── oracle_chain.py          # 核心模块（重构版）
├── proposer_node.py         # 提案节点
├── miner_node.py            # 矿工节点
├── config_loader.py         # 配置管理
├── logger.py               # 日志系统
├── http_client.py          # HTTP客户端
├── clustering.py           # 聚类算法
├── storage.py              # 存储层
├── data_extractors.py      # 数据提取器
├── generate_virtual_sources.py  # 虚拟数据生成
├── logs/                   # 日志目录
└── state/                  # 状态数据目录
    ├── data_sources.json   # 真实数据源
    ├── virtual_sources.json # 虚拟数据源
    ├── master_table.json   # 主表（总表）
    ├── chain.json          # 区块链记录
    ├── proposals/          # 提案目录
    └── backups/           # 自动备份
```

## ⚙️ 配置系统

### 主配置文件 (`config.yaml`)
```yaml
# 网络配置
network:
  timeout_sec: 5.0          # HTTP请求超时
  retries: 3                # 重试次数
  concurrent_requests: 10   # 并发请求限制

# 聚类配置
clustering:
  k: 5                      # K-means聚类数量
  cache_enabled: true       # 启用聚类缓存
  cache_ttl_sec: 300        # 缓存过期时间

# 评估权重
evaluation:
  weights:
    accuracy: 0.35          # 准确度权重
    availability: 0.15      # 可用性权重
    response_time: 0.15     # 响应时间权重
    # ... 其他权重配置

# 日志配置
logging:
  level: "INFO"             # 日志级别
  file_enabled: true        # 启用文件日志
  file_path: "logs/oracle.log"
  console_enabled: true     # 启用控制台输出
```

### 环境变量覆盖
```bash
# 覆盖网络超时
ORACLE_NETWORK_TIMEOUT_SEC=10 python3 proposer_node.py

# 覆盖日志级别
ORACLE_LOGGING_LEVEL=DEBUG python3 miner_node.py
```

## 🔧 安装和运行

### 1. 初始化系统
```bash
cd "/Users/dusko/Desktop/论文提交最终版/code"

# 生成虚拟数据源（首次运行）
python3 generate_virtual_sources.py
```

### 2. 启动矿工节点
```bash
# 基础启动
python3 miner_node.py --id miner-1 --quorum 3

# 高级配置
python3 miner_node.py --id miner-cluster-1 --quorum 3 --cluster-sample 1
```

参数说明：
- `--id`: 矿工节点ID
- `--quorum`: 共识门限（建议3-5）
- `--cluster-sample`: 每次聚类采样的数据源数量

### 3. 启动提案节点
```bash
# 启动多个提案节点（建议3-5个）
python3 proposer_node.py --id proposer-1
python3 proposer_node.py --id proposer-2
python3 proposer_node.py --id proposer-3

# 重置并使用种子数据
python3 proposer_node.py --id proposer-1 --reset-seed
```

### 4. 动态添加数据源

在提案节点终端输入：
```bash
# 基础添加（需要矿工评估特征）
add <key> <category> <url>

# 预评估添加（提案节点先评估特征）
addf <key> <category> <url>
```

示例：
```bash
addf btc_binance bitcoin_price https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
addf eth_coinbase ethereum_price https://api.exchange.coinbase.com/products/ETH-USD/ticker
```

## 📊 评估系统

### 7维评估特征
1. **准确度 (35%)** - 与参考价格的偏差
2. **可用性 (15%)** - 历史成功率
3. **响应时间 (15%)** - API响应延迟
4. **更新频率 (10%)** - 数据新鲜度
5. **数据完整性 (10%)** - 数据完整性
6. **错误率 (10%)** - 历史错误率
7. **历史表现 (5%)** - 长期稳定性

### 聚类评级
- 使用K-means聚类算法将数据源分为5个等级：**A+、A、B、C、D**
- 支持聚类结果缓存，提升性能
- 每类数据源按等级排序维护

### 共识机制
1. **ADD提案** - 添加新数据源，矿工进行聚类评级后出块
2. **CLUSTER提案** - 周期性聚类维护，更新系统评级

## 📈 性能优化

### 聚类性能
- **缓存机制**: 相同数据的聚类结果缓存5分钟
- **增量采样**: 每次仅更新部分数据源特征
- **并行处理**: 支持并发HTTP请求

### 网络优化
- **重试机制**: 自动重试失败的网络请求
- **超时控制**: 可配置的超时时间
- **并发限制**: 防止过多并发请求

### 存储优化
- **文件锁**: 防止并发访问冲突
- **原子写入**: 保证数据一致性
- **自动备份**: 定期备份重要数据

## 📋 监控和调试

### 日志系统
```bash
# 查看实时日志
tail -f logs/oracle.log

# 设置调试级别
ORACLE_LOGGING_LEVEL=DEBUG python3 proposer_node.py --id proposer-1
```

### 性能监控
系统提供内置性能监控：
- HTTP请求耗时统计
- 聚类算法性能追踪
- 文件操作时间统计
- 内存使用情况

### 配置验证
```bash
# 验证配置文件
python3 config_loader.py

# 测试HTTP客户端
python3 http_client.py

# 测试聚类算法
python3 clustering.py
```

## 🔧 故障排除

### 常见问题

**1. 提案长期未完成**
- 检查提案节点数量是否足够（建议3-5个）
- 确认网络连接正常
- 查看日志中的错误信息

**2. 聚类性能慢**
- 调整 `cluster_sample` 参数减少采样数量
- 启用聚类缓存
- 检查虚拟数据源数量

**3. 网络请求失败**
- 调整超时时间和重试次数
- 检查API URL的有效性
- 验证网络连接

### 恢复机制
```bash
# 使用备份文件恢复
cp oracle_chain_original.py oracle_chain.py
cp proposer_node.py.backup proposer_node.py
cp miner_node.py.backup miner_node.py

# 清理状态重新开始
rm -rf state/
python3 generate_virtual_sources.py
```

## 🎯 扩展建议

### 学术研究方向
1. **共识算法改进**
   - 实现PBFT或Tendermint
   - 添加节点信誉系统
   - 支持拜占庭容错

2. **评估模型优化**
   - 机器学习评估模型
   - 时间序列分析
   - 异常检测算法

3. **性能扩展**
   - 分布式聚类算法
   - 流式数据处理
   - 大规模节点支持

### 实用功能增强
1. **Web界面** - 可视化监控面板
2. **API接口** - RESTful API支持
3. **数据库支持** - 替代文件存储
4. **容器化部署** - Docker支持

## 📄 许可证

本项目仅用于学术研究目的。

## 📞 技术支持

如遇问题，请查看：
1. `logs/oracle.log` - 详细日志
2. `MIGRATION_GUIDE.md` - 迁移指南
3. 配置文件 `config.yaml` - 参数调整

---

**重要提醒**: 本系统已完成模块化重构，提供更好的性能、可维护性和可扩展性。原始文件已备份为 `*.backup` 格式。
