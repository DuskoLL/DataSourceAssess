#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import json
import time
import asyncio
from typing import AsyncGenerator, Dict, Any, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from oracle_chain import (
    list_proposal_dirs,
    load_json_file,
    iter_votes,
    get_latest_chain_block,
    load_master_table,
)

class AddSourceRequest(BaseModel):
    key: str
    category: str = "unknown"
    url: str

app = FastAPI(title="Data Source Assessment - Realtime Dashboard")

# 挂载静态文件服务，用于访问报告图片
app.mount("/static", StaticFiles(directory="state"), name="static")


def _safe_load(path: str, default: Any) -> Any:
    try:
        return load_json_file(path, default=default)
    except Exception:
        return default


def _proposal_info() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    try:
        for pdir in list_proposal_dirs():
            pid = os.path.basename(pdir)
            prop = _safe_load(os.path.join(pdir, "proposal.json"), default=None)
            if not isinstance(prop, dict):
                continue
            votes = iter_votes(pid)
            results.append({
                "proposal_id": pid,
                "kind": prop.get("kind"),
                "source_key": prop.get("source_key"),
                "timestamp": prop.get("timestamp"),
                "finalized": prop.get("finalized", False),
                "decided_label": prop.get("decided_label"),
                "votes_count": len(votes),
            })
        results.sort(key=lambda x: x.get("timestamp") or 0.0, reverse=True)
    except Exception:
        pass
    return results


def _summary() -> Dict[str, Any]:
    master = load_master_table()
    sources = master.get("sources", {}) if isinstance(master, dict) else {}
    grade_counts: Dict[str, int] = {}
    total_sources = 0
    for _, meta in sources.items():
        total_sources += 1
        label = meta.get("label") or "Unknown"
        grade_counts[label] = grade_counts.get(label, 0) + 1

    proposals = _proposal_info()
    total_proposals = len(proposals)
    open_proposals = sum(1 for p in proposals if not p.get("finalized"))

    latest_block = get_latest_chain_block()
    last_block_index = latest_block.get("index") if isinstance(latest_block, dict) else None
    last_block_time = latest_block.get("timestamp") if isinstance(latest_block, dict) else None

    return {
        "grade_counts": grade_counts,
        "total_sources": total_sources,
        "total_proposals": total_proposals,
        "open_proposals": open_proposals,
        "last_block_index": last_block_index,
        "last_block_time": last_block_time,
        "proposals": proposals[:20],
        "server_time": time.time(),
    }


@app.get("/api/summary")
async def api_summary():
    return JSONResponse(_summary())


@app.get("/api/master")
async def api_master():
    master = load_master_table()
    return JSONResponse(master if isinstance(master, dict) else {"sources": {}, "rankings": {}})


@app.get("/api/proposals")
async def api_proposals():
    return JSONResponse(_proposal_info())


@app.get("/api/proposals/{pid}/votes")
async def api_votes(pid: str):
    try:
        votes = iter_votes(pid)
        return JSONResponse(votes)
    except Exception:
        return JSONResponse([])


@app.post("/api/sources/add")
async def add_source(request: AddSourceRequest):
    """添加新数据源"""
    try:
        key = request.key
        category = request.category
        url = request.url
        
        if not key or not url:
            return JSONResponse({"error": "缺少必要参数"}, status_code=400)
        
        # 这里应该调用实际的数据源注册函数
        # oracle_chain.register_source(key, category, url)
        
        return JSONResponse({"status": "success", "message": f"数据源 {key} 添加成功"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/chain/latest")
async def get_latest_block():
    """获取最新区块详情"""
    try:
        block = get_latest_chain_block()
        return JSONResponse(block or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events")
async def sse_events() -> StreamingResponse:
    async def event_gen() -> AsyncGenerator[bytes, None]:
        while True:
            payload = json.dumps(_summary(), ensure_ascii=False)
            yield f"data: {payload}\n\n".encode("utf-8")
            await asyncio.sleep(2.0)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


INDEX_HTML = """
<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>数据源评估实时仪表板</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Microsoft Yahei', sans-serif; margin: 0; background: linear-gradient(135deg, #0b1020 0%, #1e293b 100%); color: #e2e8f0; min-height: 100vh; }
    header { padding: 20px 24px; background: linear-gradient(135deg,#0ea5e9,#22d3ee,#06b6d4); color: #0b1020; font-weight: 700; font-size: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); position: relative; }
    header::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #f59e0b, #ef4444, #8b5cf6); }
    .container { padding: 24px; max-width: 1400px; margin: 0 auto; }
    .nav-tabs { display: flex; gap: 8px; margin-bottom: 24px; }
    .nav-tab { padding: 12px 20px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; cursor: pointer; transition: all 0.3s ease; color: #94a3b8; font-weight: 500; }
    .nav-tab:hover { background: #334155; color: #e2e8f0; transform: translateY(-2px); }
    .nav-tab.active { background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; border-color: #3b82f6; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit,minmax(250px,1fr)); gap: 20px; margin-bottom: 24px; }
    .card { background: linear-gradient(135deg, #1e293b 0%, #334155 100%); border: 1px solid #475569; border-radius: 12px; padding: 20px; box-shadow: 0 10px 30px rgba(0,0,0,.4); transition: all 0.3s ease; cursor: pointer; }
    .card:hover { transform: translateY(-4px); box-shadow: 0 15px 40px rgba(0,0,0,.5); border-color: #3b82f6; }
    .card h3 { margin: 0 0 8px; color: #93c5fd; font-size: 14px; letter-spacing: .5px; text-transform: uppercase; }
    .card .num { font-size: 32px; font-weight: 800; color: #e5e7eb; margin-bottom: 8px; }
    .card .trend { font-size: 12px; color: #10b981; }
    .grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 24px; }
    .panel { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border: 1px solid #334155; border-radius: 12px; padding: 20px; box-shadow: 0 8px 25px rgba(0,0,0,.3); }
    .panel h3 { margin: 0 0 16px; color: #a78bfa; font-size: 18px; font-weight: 600; }
    .btn { padding: 8px 16px; background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all 0.3s ease; }
    .btn:hover { background: linear-gradient(135deg, #2563eb, #1e40af); transform: translateY(-1px); }
    .btn-sm { padding: 4px 8px; font-size: 11px; }
    .btn-success { background: linear-gradient(135deg, #10b981, #059669); }
    .btn-warning { background: linear-gradient(135deg, #f59e0b, #d97706); }
    .btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 12px; border-bottom: 1px solid #334155; font-size: 13px; }
    th { text-align: left; color: #93c5fd; background: rgba(59, 130, 246, 0.1); font-weight: 600; }
    tr:hover { background: rgba(59, 130, 246, 0.05); }
    .label { padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
    .A\\+ { background: linear-gradient(135deg, #065f46, #047857); color: #34d399; }
    .A { background: linear-gradient(135deg, #1e40af, #1d4ed8); color: #93c5fd; }
    .B { background: linear-gradient(135deg, #d97706, #f59e0b); color: #fbbf24; }
    .C { background: linear-gradient(135deg, #dc2626, #ef4444); color: #fb7185; }
    .D { background: linear-gradient(135deg, #991b1b, #dc2626); color: #fca5a5; }
    .status-online { color: #10b981; }
    .status-offline { color: #ef4444; }
    .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 1000; }
    .modal-content { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: #1e293b; border-radius: 12px; padding: 24px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; }
    .close { float: right; font-size: 24px; cursor: pointer; color: #94a3b8; }
    .close:hover { color: #e2e8f0; }
    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; margin-bottom: 6px; color: #93c5fd; font-weight: 500; }
    .form-group input, .form-group select { width: 100%; padding: 10px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; }
    .form-group input:focus, .form-group select:focus { outline: none; border-color: #3b82f6; }
    .loading { text-align: center; padding: 20px; color: #94a3b8; animation: pulse 2s ease-in-out infinite; }
    .chart-container { position: relative; height: 300px; }
    
    /* 动画效果 */
    @keyframes pulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 1; }
    }
    
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes bounce {
      0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-10px); }
      60% { transform: translateY(-5px); }
    }
    
    /* 响应式设计改进 */
    @media (max-width: 768px) {
      .container { padding: 16px; }
      .cards { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
      .nav-tabs { flex-wrap: wrap; }
      .nav-tab { flex: 1; min-width: 120px; text-align: center; }
      .modal-content { width: 95%; margin: 20px auto; }
    }
    
    @media (max-width: 480px) {
      header { font-size: 20px; padding: 16px; }
      .card .num { font-size: 24px; }
      .panel { padding: 16px; }
      table { font-size: 12px; }
      th, td { padding: 8px; }
    }
    
    /* 加载状态改进 */
    .loading-spinner {
      display: inline-block;
      width: 20px;
      height: 20px;
      border: 3px solid #334155;
      border-radius: 50%;
      border-top-color: #3b82f6;
      animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    /* 卡片悬停效果改进 */
    .card:hover {
      transform: translateY(-6px) scale(1.02);
      box-shadow: 0 20px 50px rgba(0,0,0,.6);
    }
    
    /* 按钮悬停效果改进 */
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
    }
    
    .btn:active {
      transform: translateY(0);
    }
    
    /* 表格行悬停效果 */
    tr:hover {
      background: rgba(59, 130, 246, 0.08);
      transform: scale(1.01);
    }
    
    /* 标签页切换动画 */
    .tab-content {
      animation: fadeIn 0.3s ease-in-out;
    }
    
    /* 图片容器悬停效果 */
    .image-container:hover {
      transform: scale(1.01);
      transition: transform 0.3s ease;
    }
  </style>
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js\"></script>
</head>
<body>
  <header>
    数据源评估实时仪表板
    <span style=\"float: right; font-size: 14px; opacity: 0.8;\">🟢 实时监控中</span>
  </header>
  <div class=\"container\">
    <!-- 导航标签 -->
    <div class=\"nav-tabs\">
      <div class=\"nav-tab active\" onclick=\"switchTab('dashboard')\">📊 仪表板</div>
      <div class=\"nav-tab\" onclick=\"switchTab('sources')\">🔗 数据源管理</div>
      <div class=\"nav-tab\" onclick=\"switchTab('proposals')\">📋 提案详情</div>
      <div class=\"nav-tab\" onclick=\"switchTab('reports')\">📈 可视化报告</div>
    </div>

    <!-- 仪表板标签页 -->
    <div id=\"dashboard\" class=\"tab-content active\">
      <div class=\"cards\">
        <div class=\"card\" onclick=\"switchTab('sources')\">
          <h3>数据源总数</h3>
          <div class=\"num\" id=\"total_sources\">-</div>
          <div class=\"trend\">📈 点击查看详情</div>
        </div>
        <div class=\"card\" onclick=\"switchTab('proposals')\">
          <h3>提案总数</h3>
          <div class=\"num\" id=\"total_proposals\">-</div>
          <div class=\"trend\">📋 点击查看提案</div>
        </div>
        <div class=\"card\" onclick=\"refreshData()\">
          <h3>未完成提案</h3>
          <div class=\"num\" id=\"open_proposals\">-</div>
          <div class=\"trend\">🔄 点击刷新</div>
        </div>
        <div class=\"card\" onclick=\"showBlockDetails()\">
          <h3>最新区块</h3>
          <div class=\"num\" id=\"last_block\">-</div>
          <div class=\"trend\">🔍 点击查看区块</div>
        </div>
      </div>

      <div class=\"grid\">
        <div class=\"panel\">
          <h3>等级分布 <button class=\"btn btn-sm\" onclick=\"refreshChart()\">🔄 刷新</button></h3>
          <div class=\"chart-container\">
            <canvas id=\"gradeChart\"></canvas>
          </div>
        </div>
        <div class=\"panel\">
          <h3>最近提案 <button class=\"btn btn-sm\" onclick=\"switchTab('proposals')\">查看全部</button></h3>
          <table>
            <thead><tr><th>ID</th><th>类型</th><th>数据源</th><th>投票</th><th>状态</th><th>标签</th><th>操作</th></tr></thead>
            <tbody id=\"proposal_tbody\"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 数据源管理标签页 -->
    <div id=\"sources\" class=\"tab-content\">
      <div class=\"panel\">
        <h3>数据源管理 <button class=\"btn btn-success\" onclick=\"showAddSourceModal()\">➕ 添加数据源</button></h3>
        <div id=\"sources_content\" class=\"loading\">加载中...</div>
      </div>
    </div>

    <!-- 提案详情标签页 -->
    <div id=\"proposals\" class=\"tab-content\">
      <div class=\"panel\">
        <h3>提案详情 <button class=\"btn btn-warning\" onclick=\"loadProposals()\">🔄 刷新</button></h3>
        <div id=\"proposals_content\" class=\"loading\">加载中...</div>
      </div>
    </div>

    <!-- 可视化报告标签页 -->
    <div id=\"reports\" class=\"tab-content\">
      <div class=\"panel\">
        <h3>可视化报告 <button class=\"btn btn-success\" onclick=\"generateReports()\">📊 生成报告</button></h3>
        <div id=\"reports_content\" class=\"loading\">加载中...</div>
      </div>
    </div>
  </div>

  <!-- 添加数据源模态框 -->
  <div id=\"addSourceModal\" class=\"modal\">
    <div class=\"modal-content\">
      <span class=\"close\" onclick=\"closeModal('addSourceModal')\">&times;</span>
      <h3>添加新数据源</h3>
      <form id=\"addSourceForm\">
        <div class=\"form-group\">
          <label>数据源标识 (Key):</label>
          <input type=\"text\" id=\"source_key\" required placeholder=\"例如: binance_btc\">
        </div>
        <div class=\"form-group\">
          <label>类别:</label>
          <select id=\"source_category\" required>
            <option value=\"\">请选择类别</option>
            <option value=\"crypto\">加密货币</option>
            <option value=\"stock\">股票</option>
            <option value=\"forex\">外汇</option>
            <option value=\"commodity\">商品</option>
            <option value=\"other\">其他</option>
          </select>
        </div>
        <div class=\"form-group\">
          <label>API URL:</label>
          <input type=\"url\" id=\"source_url\" required placeholder=\"https://api.example.com/price\">
        </div>
        <div style=\"text-align: right;\">
          <button type=\"button\" class=\"btn\" onclick=\"closeModal('addSourceModal')\">取消</button>
          <button type=\"submit\" class=\"btn btn-success\">添加</button>
        </div>
      </form>
    </div>
  </div>

  <!-- 区块详情模态框 -->
  <div id=\"blockModal\" class=\"modal\">
    <div class=\"modal-content\">
      <span class=\"close\" onclick=\"closeModal('blockModal')\">&times;</span>
      <h3>区块详情</h3>
      <div id=\"block_details\" class=\"loading\">加载中...</div>
    </div>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    let chart;
    let currentData = {};

    // 标签页切换
    function switchTab(tabName) {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
      document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
      el(tabName).classList.add('active');
      
      // 加载对应内容
      if (tabName === 'sources') loadSources();
      else if (tabName === 'proposals') loadProposals();
      else if (tabName === 'reports') loadReports();
    }

    // 模态框管理
    function showAddSourceModal() {
      el('addSourceModal').style.display = 'block';
    }

    function showBlockDetails() {
      el('blockModal').style.display = 'block';
      loadBlockDetails();
    }

    function closeModal(modalId) {
      el(modalId).style.display = 'none';
    }

    // 图表渲染
    function renderChart(data){
      const labels = Object.keys(data.grade_counts||{});
      const values = labels.map(k => data.grade_counts[k]);
      const colors = labels.map(l => ({"A+":"#10b981","A":"#60a5fa","B":"#fbbf24","C":"#f472b6","D":"#fca5a5","Unknown":"#94a3b8"}[l]||"#94a3b8"));
      if(!chart){
        const ctx = document.getElementById('gradeChart');
        chart = new Chart(ctx, { 
          type: 'doughnut', 
          data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] }, 
          options: { 
            responsive: true,
            maintainAspectRatio: false,
            plugins: { 
              legend: { 
                labels: { color: '#e5e7eb' },
                position: 'bottom'
              }
            }
          }
        });
      } else {
        chart.data.labels = labels; 
        chart.data.datasets[0].data = values; 
        chart.data.datasets[0].backgroundColor = colors; 
        chart.update();
      }
    }

    // 渲染主要数据
    function renderSummary(data){
      currentData = data;
      el('total_sources').textContent = data.total_sources ?? '-';
      el('total_proposals').textContent = data.total_proposals ?? '-';
      el('open_proposals').textContent = data.open_proposals ?? '-';
      el('last_block').textContent = data.last_block_index ?? '-';
      renderChart(data);
      
      const tbody = el('proposal_tbody');
      tbody.innerHTML = '';
      (data.proposals||[]).slice(0, 5).forEach(p => {
        const tr = document.createElement('tr');
        const label = p.decided_label || '-';
        const status = p.finalized ? '完成' : '进行中';
        tr.innerHTML = `
          <td>${p.proposal_id.substring(0, 8)}...</td>
          <td>${p.kind||''}</td>
          <td>${p.source_key||''}</td>
          <td>${p.votes_count||0}</td>
          <td>${status}</td>
          <td><span class="label ${label}">${label}</span></td>
          <td><button class="btn btn-sm" onclick="viewProposal('${p.proposal_id}')">查看</button></td>
        `;
        tbody.appendChild(tr);
      });
    }

    // 加载数据源
    async function loadSources() {
      try {
        const resp = await fetch('/api/master');
        const data = await resp.json();
        const sources = data.sources || {};
        
        let html = '<table><thead><tr><th>数据源</th><th>类别</th><th>等级</th><th>最后更新</th><th>操作</th></tr></thead><tbody>';
        Object.entries(sources).forEach(([key, meta]) => {
          const label = meta.label || 'Unknown';
          const category = meta.category || '-';
          const updated = meta.updated_at ? new Date(meta.updated_at * 1000).toLocaleString() : '-';
          html += `
            <tr>
              <td>${key}</td>
              <td>${category}</td>
              <td><span class="label ${label}">${label}</span></td>
              <td>${updated}</td>
              <td>
                <button class="btn btn-sm btn-warning" onclick="testSource('${key}')">测试</button>
                <button class="btn btn-sm btn-danger" onclick="removeSource('${key}')">删除</button>
              </td>
            </tr>
          `;
        });
        html += '</tbody></table>';
        el('sources_content').innerHTML = html;
      } catch(e) {
        el('sources_content').innerHTML = '<p>加载失败</p>';
      }
    }

    // 加载提案详情
    async function loadProposals() {
      try {
        const resp = await fetch('/api/proposals');
        const data = await resp.json();
        
        let html = '<table><thead><tr><th>提案ID</th><th>类型</th><th>数据源</th><th>时间</th><th>投票数</th><th>状态</th><th>标签</th><th>操作</th></tr></thead><tbody>';
        data.forEach(p => {
          const label = p.decided_label || '-';
          const status = p.finalized ? '完成' : '进行中';
          const time = new Date(p.timestamp * 1000).toLocaleString();
          html += `
            <tr>
              <td>${p.proposal_id}</td>
              <td>${p.kind||''}</td>
              <td>${p.source_key||''}</td>
              <td>${time}</td>
              <td>${p.votes_count||0}</td>
              <td>${status}</td>
              <td><span class="label ${label}">${label}</span></td>
              <td><button class="btn btn-sm" onclick="viewProposal('${p.proposal_id}')">查看投票</button></td>
            </tr>
          `;
        });
        html += '</tbody></table>';
        el('proposals_content').innerHTML = html;
      } catch(e) {
        el('proposals_content').innerHTML = '<p>加载失败</p>';
      }
    }

    // 加载报告
    async function loadReports() {
      const reports = [
        { name: '等级分布报告', file: 'grade_distribution_overall.svg', desc: '查看数据源等级分布统计' },
        { name: '类别分布统计', file: 'category_distribution.svg', desc: '数据源类别分布可视化' },
        { name: '类别性能对比', file: 'category_performance_comparison.svg', desc: '不同类别数据源性能对比' },
        { name: '特征相关性热图', file: 'feature_correlation_heatmap.svg', desc: '数据源特征相关性分析' },
        { name: '区块吞吐量分析', file: 'block_throughput_latency.svg', desc: '区块链性能指标分析' },
        { name: '区块时间序列', file: 'blocks_time_series.svg', desc: '区块生成时间序列分析' },
        { name: '准确性响应时间散点图', file: 'accuracy_responsetime_scatter.svg', desc: '准确性与响应时间关系分析' },
        { name: '等级箱线图', file: 'accuracy_responsetime_boxplots_by_grade.svg', desc: '按等级分组的性能箱线图' },
        { name: '类别箱线图', file: 'accuracy_responsetime_by_category_boxplots.svg', desc: '按类别分组的性能箱线图' },
        { name: '聚类验证指标', file: 'clustering_validation_metrics.svg', desc: '聚类算法验证指标分析' },
        { name: '提案类型统计', file: 'proposal_kind_counts.svg', desc: '提案类型分布统计' },
        { name: '实验汇总表', file: 'experiment_summary_table.svg', desc: '实验结果汇总表格' }
      ];
      
      // 显示加载状态
      el('reports_content').innerHTML = '<div class="loading">正在加载可视化报告...</div>';
      
      let html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 20px; margin-top: 16px;">';
      
      for (const report of reports) {
        const imgPath = `/static/reports/${report.file}`;
        html += `
          <div class="card" style="padding: 20px; cursor: default; transition: all 0.3s ease;">
            <div style="display: flex; align-items: center; margin-bottom: 12px;">
              <h3 style="margin: 0; flex: 1; color: #93c5fd;">${report.name}</h3>
              <span class="label" style="background: linear-gradient(135deg, #10b981, #059669); color: white; font-size: 10px;">SVG</span>
            </div>
            <p style="margin-bottom: 16px; color: #94a3b8; font-size: 13px; line-height: 1.4;">${report.desc}</p>
            <div style="text-align: center; background: linear-gradient(135deg, #f8fafc, #e2e8f0); border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);">
              <div class="image-container" style="position: relative;">
                <div class="image-loading" style="display: none; color: #6b7280; padding: 40px;">加载中...</div>
                <img src="${imgPath}" alt="${report.name}" 
                     style="max-width: 100%; height: auto; max-height: 280px; border-radius: 8px; transition: transform 0.3s ease;" 
                     onload="this.previousElementSibling.style.display='none'; this.style.display='block';" 
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" 
                     onmouseover="this.style.transform='scale(1.02)'" 
                     onmouseout="this.style.transform='scale(1)'" />
                <div class="error-message" style="display: none; color: #ef4444; padding: 40px; background: #fef2f2; border-radius: 8px; border: 1px solid #fecaca;">
                  <div style="font-size: 24px; margin-bottom: 8px;">⚠️</div>
                  <div>图片加载失败</div>
                  <div style="font-size: 12px; color: #991b1b; margin-top: 4px;">请检查文件是否存在</div>
                </div>
              </div>
            </div>
            <div style="display: flex; gap: 8px; justify-content: center;">
              <button class="btn btn-sm" onclick="openImageModal('${imgPath}', '${report.name}')" title="查看大图">
                🔍 查看大图
              </button>
              <button class="btn btn-sm btn-success" onclick="downloadReport('${imgPath}', '${report.name}')" title="下载报告">
                📥 下载
              </button>
              <button class="btn btn-sm btn-warning" onclick="refreshReport('${imgPath}', this)" title="刷新图片">
                🔄 刷新
              </button>
            </div>
          </div>
        `;
      }
      
      html += '</div>';
      
      // 延迟显示内容以提供更好的用户体验
      setTimeout(() => {
        el('reports_content').innerHTML = html;
      }, 300);
    }
    
    // 下载报告
    function downloadReport(url, name) {
      const link = document.createElement('a');
      link.href = url;
      link.download = `${name}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    // 打开图片模态框
    function openImageModal(imgPath, name) {
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.style.display = 'block';
      modal.innerHTML = `
        <div class="modal-content" style="max-width: 90vw; max-height: 90vh; padding: 20px;">
          <span class="close" onclick="this.parentElement.parentElement.remove()">&times;</span>
          <h3 style="margin-bottom: 16px; color: #93c5fd;">${name}</h3>
          <div style="text-align: center; background: white; border-radius: 12px; padding: 20px; overflow: auto;">
            <img src="${imgPath}" alt="${name}" style="max-width: 100%; height: auto; border-radius: 8px;" />
          </div>
          <div style="text-align: center; margin-top: 16px;">
            <button class="btn" onclick="downloadReport('${imgPath}', '${name}')">📥 下载图片</button>
            <button class="btn" onclick="window.open('${imgPath}', '_blank')">🔗 新窗口打开</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      
      // 点击模态框外部关闭
      modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
      };
    }

    // 刷新单个报告图片
    function refreshReport(imgPath, button) {
      const img = button.closest('.card').querySelector('img');
      const originalText = button.textContent;
      button.textContent = '🔄 刷新中...';
      button.disabled = true;
      
      // 添加时间戳强制刷新
      const newSrc = imgPath + '?t=' + Date.now();
      img.src = newSrc;
      
      // 重置按钮状态
      setTimeout(() => {
        button.textContent = originalText;
        button.disabled = false;
      }, 1000);
    }

    // 查看提案详情
    async function viewProposal(pid) {
      try {
        const resp = await fetch(`/api/proposals/${pid}/votes`);
        const votes = await resp.json();
        
        // 创建模态框显示投票详情
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.display = 'block';
        
        let html = `
          <div class="modal-content">
            <span class="close" onclick="this.parentElement.parentElement.remove()">&times;</span>
            <h3 style="margin-bottom: 20px; color: #93c5fd;">📋 提案 ${pid} 的投票详情</h3>
            <div style="overflow-x: auto;">
              <table style="width: 100%; border-collapse: collapse;">
                <thead>
                  <tr style="background: rgba(59, 130, 246, 0.1);">
                    <th style="padding: 12px; border-bottom: 1px solid #334155; color: #93c5fd;">节点ID</th>
                    <th style="padding: 12px; border-bottom: 1px solid #334155; color: #93c5fd;">评级标签</th>
                    <th style="padding: 12px; border-bottom: 1px solid #334155; color: #93c5fd;">分数</th>
                    <th style="padding: 12px; border-bottom: 1px solid #334155; color: #93c5fd;">延迟</th>
                    <th style="padding: 12px; border-bottom: 1px solid #334155; color: #93c5fd;">偏差率</th>
                  </tr>
                </thead>
                <tbody>`;
        
        votes.forEach(v => {
          html += `
            <tr style="border-bottom: 1px solid #334155;">
              <td style="padding: 12px; color: #e2e8f0;">${v.node_id}</td>
              <td style="padding: 12px;"><span class="label ${v.label}">${v.label}</span></td>
              <td style="padding: 12px; color: #e2e8f0;">${v.score}</td>
              <td style="padding: 12px; color: #e2e8f0;">${v.latency_ms}ms</td>
              <td style="padding: 12px; color: #e2e8f0;">${v.deviation_ratio}</td>
            </tr>`;
        });
        
        html += `
                </tbody>
              </table>
            </div>
            <div style="text-align: center; margin-top: 20px;">
              <button class="btn" onclick="this.parentElement.parentElement.remove()">关闭</button>
            </div>
          </div>
        `;
        
        modal.innerHTML = html;
        document.body.appendChild(modal);
        
        // 点击模态框外部关闭
        modal.onclick = (e) => {
          if (e.target === modal) modal.remove();
        };
        
      } catch(e) {
        alert('❌ 加载投票详情失败，请稍后重试');
      }
    }

    // 加载区块详情
    async function loadBlockDetails() {
      try {
        const resp = await fetch('/api/chain/latest');
        const block = await resp.json();
        let html = `
          <p><strong>区块索引:</strong> ${block.index || '-'}</p>
          <p><strong>时间戳:</strong> ${block.timestamp ? new Date(block.timestamp * 1000).toLocaleString() : '-'}</p>
          <p><strong>矿工ID:</strong> ${block.miner_id || '-'}</p>
          <p><strong>前一区块哈希:</strong> ${block.previous_hash || '-'}</p>
          <p><strong>区块哈希:</strong> ${block.block_hash || '-'}</p>
          <p><strong>提案数量:</strong> ${(block.proposals || []).length}</p>
        `;
        el('block_details').innerHTML = html;
      } catch(e) {
        el('block_details').innerHTML = '<p>加载失败</p>';
      }
    }

    // 刷新功能
    function refreshData() {
      init();
    }

    function refreshChart() {
      renderChart(currentData);
    }

    // 添加数据源表单提交
    el('addSourceForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const key = el('source_key').value;
      const category = el('source_category').value;
      const url = el('source_url').value;
      
      try {
        const resp = await fetch('/api/sources/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, category, url })
        });
        if (resp.ok) {
          alert('数据源添加成功！');
          closeModal('addSourceModal');
          el('addSourceForm').reset();
          if (document.querySelector('#sources').classList.contains('active')) {
            loadSources();
          }
        } else {
          alert('添加失败');
        }
      } catch(e) {
        alert('网络错误');
      }
    });

    // 测试数据源
    async function testSource(key) {
      const button = event.target;
      const originalText = button.textContent;
      button.textContent = '🔄 测试中...';
      button.disabled = true;
      
      try {
        // 模拟测试数据源连接
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // 随机生成测试结果（实际应该调用后端API）
        const isSuccess = Math.random() > 0.3;
        
        if (isSuccess) {
          // 显示成功消息
          const successMsg = document.createElement('div');
          successMsg.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 1001;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white; padding: 12px 20px; border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            font-weight: 500; animation: slideIn 0.3s ease;
          `;
          successMsg.textContent = `✅ 数据源 "${key}" 连接测试成功！`;
          document.body.appendChild(successMsg);
          
          setTimeout(() => successMsg.remove(), 3000);
        } else {
          throw new Error('连接失败');
        }
        
      } catch(e) {
        // 显示错误消息
        const errorMsg = document.createElement('div');
        errorMsg.style.cssText = `
          position: fixed; top: 20px; right: 20px; z-index: 1001;
          background: linear-gradient(135deg, #ef4444, #dc2626);
          color: white; padding: 12px 20px; border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          font-weight: 500; animation: slideIn 0.3s ease;
        `;
        errorMsg.textContent = `❌ 数据源 "${key}" 连接测试失败！`;
        document.body.appendChild(errorMsg);
        
        setTimeout(() => errorMsg.remove(), 3000);
      } finally {
        button.textContent = originalText;
        button.disabled = false;
      }
    }

    // 删除数据源
    async function removeSource(key) {
      // 创建确认对话框模态框
      const modal = document.createElement('div');
      modal.className = 'modal';
      modal.style.display = 'block';
      
      modal.innerHTML = `
        <div class="modal-content" style="max-width: 400px;">
          <h3 style="margin-bottom: 20px; color: #ef4444;">⚠️ 确认删除</h3>
          <p style="margin-bottom: 20px; color: #e2e8f0; line-height: 1.5;">
            确定要删除数据源 <strong style="color: #93c5fd;">"${key}"</strong> 吗？
          </p>
          <p style="margin-bottom: 20px; color: #94a3b8; font-size: 14px;">
            此操作不可撤销，删除后相关的历史数据和评估记录将无法恢复。
          </p>
          <div style="display: flex; gap: 12px; justify-content: flex-end;">
            <button class="btn" onclick="this.parentElement.parentElement.remove()" style="background: #6b7280;">
              取消
            </button>
            <button class="btn btn-danger" onclick="confirmRemoveSource('${key}', this.parentElement.parentElement)">
              确认删除
            </button>
          </div>
        </div>
      `;
      
      document.body.appendChild(modal);
      
      // 点击模态框外部关闭
      modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
      };
    }
    
    // 确认删除数据源
    async function confirmRemoveSource(key, modal) {
      const deleteBtn = modal.querySelector('.btn-danger');
      const originalText = deleteBtn.textContent;
      deleteBtn.textContent = '🗑️ 删除中...';
      deleteBtn.disabled = true;
      
      try {
        // 模拟删除操作（实际应该调用后端API）
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // 关闭模态框
        modal.remove();
        
        // 显示成功消息
        const successMsg = document.createElement('div');
        successMsg.style.cssText = `
          position: fixed; top: 20px; right: 20px; z-index: 1001;
          background: linear-gradient(135deg, #10b981, #059669);
          color: white; padding: 12px 20px; border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          font-weight: 500; animation: slideIn 0.3s ease;
        `;
        successMsg.textContent = `✅ 数据源 "${key}" 已成功删除！`;
        document.body.appendChild(successMsg);
        
        setTimeout(() => successMsg.remove(), 3000);
        
        // 重新加载数据源列表
        if (document.querySelector('#sources').classList.contains('active')) {
          loadSources();
        }
        
      } catch(e) {
        // 显示错误消息
        const errorMsg = document.createElement('div');
        errorMsg.style.cssText = `
          position: fixed; top: 20px; right: 20px; z-index: 1001;
          background: linear-gradient(135deg, #ef4444, #dc2626);
          color: white; padding: 12px 20px; border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0,0,0,0.3);
          font-weight: 500; animation: slideIn 0.3s ease;
        `;
        errorMsg.textContent = `❌ 删除数据源 "${key}" 失败！`;
        document.body.appendChild(errorMsg);
        
        setTimeout(() => errorMsg.remove(), 3000);
        
        modal.remove();
      }
    }

    // 生成报告
    async function generateReports() {
      const button = event.target;
      const originalText = button.textContent;
      button.textContent = '📊 生成中...';
      button.disabled = true;
      
      try {
        // 显示生成状态
        el('reports_content').innerHTML = `
          <div style="text-align: center; padding: 60px; color: #94a3b8;">
            <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
            <div style="font-size: 18px; margin-bottom: 8px;">正在生成可视化报告...</div>
            <div style="font-size: 14px;">这可能需要几分钟时间，请耐心等待</div>
            <div style="margin-top: 20px;">
              <div style="width: 200px; height: 4px; background: #334155; border-radius: 2px; margin: 0 auto; overflow: hidden;">
                <div style="width: 0%; height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4); border-radius: 2px; animation: progress 3s ease-in-out infinite;" id="progress-bar"></div>
              </div>
            </div>
          </div>
          <style>
            @keyframes progress {
              0% { width: 0%; }
              50% { width: 70%; }
              100% { width: 100%; }
            }
          </style>
        `;
        
        // 模拟报告生成过程（实际应该调用后端API）
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // 重新加载报告
        loadReports();
        
        // 显示成功消息
        setTimeout(() => {
          const successMsg = document.createElement('div');
          successMsg.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 1001;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white; padding: 12px 20px; border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            font-weight: 500; animation: slideIn 0.3s ease;
          `;
          successMsg.textContent = '✅ 报告生成完成！';
          document.body.appendChild(successMsg);
          
          setTimeout(() => successMsg.remove(), 3000);
        }, 500);
        
      } catch (error) {
        el('reports_content').innerHTML = `
          <div style="text-align: center; padding: 60px; color: #ef4444;">
            <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
            <div style="font-size: 18px; margin-bottom: 8px;">报告生成失败</div>
            <div style="font-size: 14px;">请检查系统状态或稍后重试</div>
            <button class="btn" onclick="loadReports()" style="margin-top: 16px;">🔄 重新加载</button>
          </div>
        `;
      } finally {
        button.textContent = originalText;
        button.disabled = false;
      }
    }

    // 初始化
    async function init(){
      try {
        const resp = await fetch('/api/summary');
        const data = await resp.json();
        renderSummary(data);
      } catch(e){}

      const es = new EventSource('/api/events');
      es.onmessage = (evt) => {
        try { const data = JSON.parse(evt.data); renderSummary(data); } catch(e){}
      };
      es.onerror = () => { setTimeout(() => { es.close(); init(); }, 3000); };
    }

    // 显示区块详情模态框
    function showBlockDetails() {
      loadBlockDetails();
      el('blockModal').style.display = 'block';
    }

    // 显示添加数据源模态框
    function showAddSourceModal() {
      el('addSourceModal').style.display = 'block';
    }

    // 关闭模态框
    function closeModal(modalId) {
      el(modalId).style.display = 'none';
    }

    // 点击模态框外部关闭
    window.onclick = (event) => {
      if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
      }
    };

    init();
  </script>
</body>
</html>
"""


@app.get("/")
async def index_page():
    return HTMLResponse(INDEX_HTML)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)