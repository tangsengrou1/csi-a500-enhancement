"""Build the descriptive 2020–2022 factor quality report from local factor matrices."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from plotly.offline.offline import get_plotlyjs


START = pd.Timestamp("2020-01-01")
END = pd.Timestamp("2022-12-31")
PERIODS_PER_YEAR = 52
COST_RATE = 20 / 10_000


def bundled_plotly_js() -> str:
    """Keep the offline bundle free of trailing whitespace in Git diffs."""
    return "\n".join(line.rstrip() for line in get_plotlyjs().splitlines())


def rank_weights(values: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return 0–1 average ranks and dollar-neutral signed weights."""
    values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 3 or values.nunique() < 2:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
    ranks = (values.rank(method="average") - 1) / (len(values) - 1)
    long_raw = (ranks - 0.5).clip(lower=0)
    short_raw = (0.5 - ranks).clip(lower=0)
    if long_raw.sum() <= 0 or short_raw.sum() <= 0:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
    longs = 0.5 * long_raw / long_raw.sum()
    shorts = -0.5 * short_raw / short_raw.sum()
    return ranks, longs, shorts


def metrics(returns: pd.Series) -> dict[str, float]:
    x = returns.dropna().astype(float)
    if x.empty:
        return dict(weeks=0, cumulative_return=np.nan, annual_return=np.nan, annual_vol=np.nan,
                    sharpe=np.nan, max_drawdown=np.nan, var_5=np.nan, cvar_5=np.nan)
    nav = (1 + x).cumprod()
    vol = x.std(ddof=1) * math.sqrt(PERIODS_PER_YEAR) if len(x) > 1 else np.nan
    annual = float(nav.iloc[-1] ** (PERIODS_PER_YEAR / len(x)) - 1) if nav.iloc[-1] > 0 else np.nan
    q = x.quantile(0.05)
    return dict(weeks=len(x), cumulative_return=float(nav.iloc[-1] - 1), annual_return=annual,
                annual_vol=float(vol), sharpe=float(x.mean() * PERIODS_PER_YEAR / vol) if vol > 0 else np.nan,
                max_drawdown=float((nav / nav.cummax() - 1).min()), var_5=float(q),
                cvar_5=float(x[x <= q].mean()))


def finite_or_none(value):
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    return value


def report_factor(path: Path, close: pd.DataFrame, amount: pd.DataFrame,
                  periods: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]],
                  family: str) -> tuple[dict, pd.DataFrame, list[dict]]:
    frame = pd.read_parquet(path)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.loc[(frame.index >= START) & (frame.index <= END)]
    factor = path.stem
    weekly = []
    previous = pd.Series(dtype=float)
    all_finite = 0
    all_possible = 0
    inf_count = 0
    constant_dates = 0
    yearly_ic: dict[int, list[float]] = {}
    issues = []
    for signal, entry, exit_date in periods:
        if signal not in frame.index:
            issues.append(dict(factor=factor, date=str(signal.date()), reason="MISSING_FACTOR_DATE"))
            continue
        raw = pd.to_numeric(frame.loc[signal], errors="coerce")
        raw = raw.reindex(close.columns)
        inf_count += int(np.isinf(raw.to_numpy(dtype=float)).sum())
        available_at_signal = close.loc[signal].notna() & close.loc[signal].gt(0)
        raw = raw.where(available_at_signal)
        all_possible += int(available_at_signal.sum())
        all_finite += int(np.isfinite(raw.to_numpy(dtype=float)).sum())
        valid = raw.replace([np.inf, -np.inf], np.nan).dropna()
        if valid.nunique() < 2:
            constant_dates += 1
        ranks, longs, shorts = rank_weights(valid)
        if ranks.empty:
            issues.append(dict(factor=factor, date=str(signal.date()), reason="INVALID_CROSS_SECTION"))
            continue
        # Execution-day price availability is known when orders are placed.
        entry_px = close.loc[entry].reindex(ranks.index)
        executable = entry_px.notna() & entry_px.gt(0)
        longs = longs[executable]
        shorts = shorts[executable]
        if longs.sum() <= 0 or shorts.sum() >= 0:
            issues.append(dict(factor=factor, date=str(signal.date()), reason="NO_EXECUTABLE_TWO_SIDED_PORTFOLIO"))
            continue
        longs = longs * (0.5 / longs.sum())
        shorts = shorts * (-0.5 / shorts.sum())
        weights = (longs.add(shorts, fill_value=0)).loc[lambda s: s != 0]
        exit_px = close.loc[exit_date].reindex(weights.index)
        if exit_px.isna().any() or exit_px.le(0).any():
            issues.append(dict(factor=factor, date=str(signal.date()), reason="MISSING_EXIT_PRICE"))
            continue
        stock_ret = exit_px / entry_px.reindex(weights.index) - 1
        long_ret = float((longs * stock_ret.reindex(longs.index)).sum())
        short_ret = float((shorts * stock_ret.reindex(shorts.index)).sum())
        turnover = float(weights.sub(previous, fill_value=0).abs().sum())
        cost = turnover * COST_RATE
        ic_idx = entry_px.index.intersection(close.loc[exit_date].dropna().index)
        fwd = close.loc[exit_date].reindex(ic_idx) / entry_px.reindex(ic_idx) - 1
        ic_frame = pd.concat([ranks.reindex(ic_idx), fwd], axis=1).dropna()
        rank_ic = float(ic_frame.iloc[:, 0].corr(ic_frame.iloc[:, 1], method="spearman")) if len(ic_frame) >= 3 and ic_frame.iloc[:, 1].nunique() > 1 else np.nan
        pearson_ic = float(ic_frame.iloc[:, 0].corr(ic_frame.iloc[:, 1])) if len(ic_frame) >= 3 and ic_frame.iloc[:, 1].nunique() > 1 else np.nan
        if np.isfinite(rank_ic):
            yearly_ic.setdefault(signal.year, []).append(rank_ic)
        amt = amount.loc[signal].reindex(weights.index)
        weekly.append(dict(factor=factor, family=family, signal_date=signal, entry_date=entry, exit_date=exit_date,
                           valid_stocks=len(ranks), long_stocks=int((weights > 0).sum()),
                           short_stocks=int((weights < 0).sum()), long_return=long_ret, short_return=short_ret,
                           gross_return=long_ret + short_ret, net_return=long_ret + short_ret - cost,
                           turnover=turnover, trading_cost=cost, rank_ic=rank_ic, pearson_ic=pearson_ic,
                           max_abs_weight=float(weights.abs().max()),
                           top10_gross_weight=float(weights.abs().nlargest(10).sum()),
                           median_amount=float(amt.median()) if amt.notna().any() else np.nan))
        previous = weights
    w = pd.DataFrame(weekly)
    total = len(periods)
    row = dict(factor=factor, family=family, scheduled_weeks=total, valid_weeks=len(w),
               invalid_weeks=total-len(w), coverage=all_finite/all_possible if all_possible else np.nan,
               inf_count=inf_count, constant_weeks=constant_dates)
    if not w.empty:
        for name, col in [('gross','gross_return'),('net','net_return'),('long','long_return'),('short','short_return')]:
            row.update({f'{name}_{k}': v for k,v in metrics(w[col]).items()})
        for col in ['rank_ic','pearson_ic','turnover','trading_cost','long_stocks','short_stocks',
                    'max_abs_weight','top10_gross_weight','median_amount']:
            row[f'{col}_mean'] = float(w[col].mean())
            if col in ['turnover','rank_ic']:
                row[f'{col}_p95'] = float(w[col].quantile(.95))
        ic = w['rank_ic'].dropna()
        row['rank_icir'] = float(ic.mean()/ic.std(ddof=1)) if len(ic)>1 and ic.std(ddof=1)>0 else np.nan
        row['rank_ic_positive_share'] = float((ic>0).mean()) if len(ic) else np.nan
        for year in [2020,2021,2022]:
            row[f'rank_ic_{year}'] = float(np.mean(yearly_ic.get(year,[]))) if yearly_ic.get(year) else np.nan
            t = w[w.signal_date.dt.year == year]
            row[f'net_return_{year}'] = float((1+t.net_return).prod()-1) if len(t) else np.nan
    return row, w, issues


def make_html(summary: pd.DataFrame, weekly: pd.DataFrame, issues: pd.DataFrame, output: Path) -> None:
    keep = ['factor','family','coverage','valid_weeks','invalid_weeks','rank_ic_mean','rank_icir',
            'rank_ic_positive_share','gross_annual_return','net_annual_return','net_annual_vol',
            'net_sharpe','net_max_drawdown','net_cvar_5','turnover_mean','trading_cost_mean',
            'max_abs_weight_mean','rank_ic_2020','rank_ic_2021','rank_ic_2022',
            'net_return_2020','net_return_2021','net_return_2022']
    records = [{k:finite_or_none(v) for k,v in r.items()} for r in summary[keep].to_dict('records')]
    series_cols = ['factor','signal_date','gross_return','net_return','long_return','short_return','rank_ic','turnover']
    series = {}
    for factor, g in weekly[series_cols].groupby('factor', sort=False):
        series[factor] = {
            'date':g.signal_date.dt.strftime('%Y-%m-%d').tolist(),
            **{c:[finite_or_none(v) for v in g[c]] for c in series_cols[2:]}
        }
    issue_counts = issues.reason.value_counts().to_dict() if not issues.empty else {}
    payload = json.dumps({'rows':records,'series':series,'issues':issue_counts},ensure_ascii=False,separators=(',',':'))
    html = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>因子质量研究报告 | 2020–2022</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f8fafc;color:#17243a;margin:0}main{max-width:1350px;margin:auto;padding:30px 24px}h1{font-size:29px;margin-bottom:7px}h2{font-size:19px;margin:30px 0 10px}.sub{color:#52627a;line-height:1.65}.note{background:#fff4db;border-left:4px solid #d79923;padding:12px 15px;margin:20px 0;line-height:1.6}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{background:white;border:1px solid #dbe2ea;border-radius:9px;padding:16px}.stat b{display:block;font-size:26px;margin-top:7px}.plots{display:grid;grid-template-columns:1fr 1fr;gap:14px}.plot{height:360px;background:white;border:1px solid #e1e7ef;border-radius:9px}.wide{grid-column:1/-1}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}input,select{font:inherit;padding:9px;border:1px solid #bac6d6;border-radius:5px;background:white}table{border-collapse:collapse;background:white;width:100%;font-size:13px}th,td{border-bottom:1px solid #e6ebf1;padding:8px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{position:sticky;top:0;background:#eef3f8;cursor:pointer}tr:hover{background:#f2f8ff}.tablebox{max-height:450px;overflow:auto;border:1px solid #dbe2ea}.detail{background:white;padding:18px;border:1px solid #dbe2ea;border-radius:9px}.small{font-size:12px;color:#596a81}@media(max-width:800px){.grid{grid-template-columns:repeat(2,1fr)}.plots{grid-template-columns:1fr}.wide{grid-column:auto}main{padding:16px}.plot{height:310px}}</style>
<script>''' + bundled_plotly_js() + '''</script></head><body><main><h1>因子质量研究报告</h1><div class="sub">Alpha158 × GTJA191 · 2020–2022 训练集 · 周频 · 0–1 截面平均秩 · 多头 50% / 空头 50%</div>
<div class="note">训练集内描述性统计，不能当作样本外预测能力。当前无历史成分股，存在股票池选择偏差；未复权收盘价可能受分红送转影响。20 bp 成本只含调仓交易成本，不含借券费、融资费和冲击成本。同期缺基准行情与行业历史数据，暂不计算 Beta、跟踪误差或行业暴露。</div>
<div id="stats" class="grid"></div><h2>全体因子概览</h2><div class="plots"><div id="coverage" class="plot"></div><div id="risk" class="plot"></div><div id="icturn" class="plot"></div><div id="family" class="plot"></div></div>
<h2>筛选与比较</h2><div class="controls"><input id="search" placeholder="搜索因子名称" aria-label="搜索因子"><select id="familyFilter" aria-label="因子家族"><option value="">全部家族</option><option value="Alpha158">Alpha158</option><option value="GTJA191">GTJA191</option></select><select id="factorSelect" aria-label="选择单个因子"></select></div><div class="tablebox"><table id="factorTable"><thead><tr><th data-key="factor">因子</th><th data-key="family">家族</th><th data-key="coverage">覆盖率</th><th data-key="valid_weeks">有效周</th><th data-key="rank_ic_mean">Rank IC</th><th data-key="rank_icir">ICIR</th><th data-key="net_annual_return">净年化收益</th><th data-key="net_annual_vol">净年化波动</th><th data-key="net_sharpe">净 Sharpe</th><th data-key="net_max_drawdown">最大回撤</th><th data-key="turnover_mean">平均换手</th></tr></thead><tbody></tbody></table></div>
<h2>单因子逐周详情</h2><div class="detail"><div id="factorMeta" class="sub"></div><div class="plots"><div id="nav" class="plot wide"></div><div id="ic" class="plot"></div><div id="turnover" class="plot"></div></div></div>
<p class="small">收益定义：下一交易日收盘建仓至下次调仓执行日收盘；成本 = 20 bp × 全部调仓权重绝对变化（含首次建仓）。排名权重与中位数距离成正比；高值做多、低值做空，不按全样本表现翻转方向。IC 为当前截面排名与同一持有期个股收益的相关系数；ICIR = 周度 Rank IC 均值 / 标准差。CVaR 为最差 5% 周收益均值。净值将有效周收益连续复利，缺失周不填收益。异常计数：<span id="issues"></span>。</p>
</main><script>const D=__PAYLOAD__;const rows=D.rows;const pct=x=>x==null?'—':(100*x).toFixed(2)+'%';const num=x=>x==null?'—':Number(x).toFixed(3);const config={responsive:true,displaylogo:false};const layout=(title,xlabel,ylabel)=>({title:{text:title,font:{size:16}},paper_bgcolor:'white',plot_bgcolor:'white',margin:{l:60,r:18,t:48,b:55},xaxis:{title:xlabel,zeroline:false,gridcolor:'#edf1f6'},yaxis:{title:ylabel,zeroline:false,gridcolor:'#edf1f6'},font:{family:'-apple-system,BlinkMacSystemFont,PingFang SC,sans-serif',size:12}});
document.getElementById('stats').innerHTML=[['因子总数',rows.length],['有效周中位数',Math.round(rows.map(x=>x.valid_weeks).sort((a,b)=>a-b)[Math.floor(rows.length/2)])],['覆盖率中位数',pct(rows.map(x=>x.coverage).sort((a,b)=>a-b)[Math.floor(rows.length/2)])],['无效组合周数',rows.reduce((a,x)=>a+x.invalid_weeks,0)]].map(([k,v])=>`<div class="stat">${k}<b>${v}</b></div>`).join('');document.getElementById('issues').textContent=JSON.stringify(D.issues);
Plotly.newPlot('coverage',[{x:rows.filter(x=>x.family==='Alpha158').map(x=>x.coverage),type:'histogram',name:'Alpha158',opacity:.72,marker:{color:'#2670b8'}},{x:rows.filter(x=>x.family==='GTJA191').map(x=>x.coverage),type:'histogram',name:'GTJA191',opacity:.72,marker:{color:'#e59b3d'}}],{...layout('数据覆盖率','有效值比例','因子数'),barmode:'overlay'},config);
const scatter=(id,xkey,ykey,title,xlab,ylab)=>{let t=['Alpha158','GTJA191'].map((f,i)=>{let a=rows.filter(r=>r.family===f&&r[xkey]!=null&&r[ykey]!=null);return{x:a.map(r=>r[xkey]),y:a.map(r=>r[ykey]),text:a.map(r=>r.factor),type:'scattergl',mode:'markers',name:f,marker:{color:i?'#e59b3d':'#2670b8',size:7,opacity:.65},hovertemplate:'%{text}<br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>'}});Plotly.newPlot(id,t,layout(title,xlab,ylab),config)};scatter('risk','net_annual_vol','net_annual_return','收益与风险','年化波动','净年化收益');scatter('icturn','turnover_mean','rank_ic_mean','预测关系与交易强度','平均换手','Rank IC');
Plotly.newPlot('family',['Alpha158','GTJA191'].map((f,i)=>({x:rows.filter(r=>r.family===f).map(r=>r.net_annual_return).filter(x=>x!=null),type:'box',name:f,marker:{color:i?'#e59b3d':'#2670b8'},boxpoints:false})),layout('家族净收益分布','年化收益','因子家族'),config);
let sortKey='factor',desc=false;const tbody=document.querySelector('#factorTable tbody');function renderTable(){let q=document.getElementById('search').value.toLowerCase(),f=document.getElementById('familyFilter').value;let a=rows.filter(r=>r.factor.toLowerCase().includes(q)&&(!f||r.family===f));a.sort((x,y)=>{let p=x[sortKey],v=y[sortKey];if(p==null)return 1;if(v==null)return -1;return (typeof p==='number'?p-v:String(p).localeCompare(String(v)))*(desc?-1:1)});tbody.innerHTML=a.map(r=>`<tr data-factor="${r.factor}"><td>${r.factor}</td><td>${r.family}</td><td>${pct(r.coverage)}</td><td>${r.valid_weeks}</td><td>${num(r.rank_ic_mean)}</td><td>${num(r.rank_icir)}</td><td>${pct(r.net_annual_return)}</td><td>${pct(r.net_annual_vol)}</td><td>${num(r.net_sharpe)}</td><td>${pct(r.net_max_drawdown)}</td><td>${pct(r.turnover_mean)}</td></tr>`).join('')};document.querySelectorAll('th[data-key]').forEach(h=>h.onclick=()=>{let k=h.dataset.key;desc=sortKey===k?!desc:false;sortKey=k;renderTable()});['search','familyFilter'].forEach(id=>document.getElementById(id).addEventListener('input',renderTable));tbody.onclick=e=>{let tr=e.target.closest('tr');if(tr){document.getElementById('factorSelect').value=tr.dataset.factor;showFactor(tr.dataset.factor)}};let sel=document.getElementById('factorSelect');sel.innerHTML=rows.map(r=>`<option value="${r.factor}">${r.factor} (${r.family})</option>`).join('');sel.onchange=()=>showFactor(sel.value);renderTable();
function nav(a){let z=1;return a.map(v=>(z*=1+(v||0)))}function showFactor(name){let s=D.series[name],r=rows.find(x=>x.factor===name);if(!s)return;document.getElementById('factorMeta').textContent=`${name} · ${r.family} · 覆盖率 ${pct(r.coverage)} · 有效 ${r.valid_weeks}/${r.valid_weeks+r.invalid_weeks} 周 · 净年化收益 ${pct(r.net_annual_return)} · 净最大回撤 ${pct(r.net_max_drawdown)}`;Plotly.react('nav',[['gross_return','多空毛收益','#7b8aa0'],['net_return','多空净收益','#2670b8'],['long_return','多头贡献','#30a57a'],['short_return','空头贡献','#dc734d']].map(([k,n,c])=>({x:s.date,y:nav(s[k]),mode:'lines',name:n,line:{color:c,width:2}})),layout('累计净值','日期','净值'),config);Plotly.react('ic',[{x:s.date,y:s.rank_ic,type:'bar',marker:{color:s.rank_ic.map(x=>x>=0?'#30a57a':'#dc734d')}}],layout('逐周 Rank IC','日期','Rank IC'),config);Plotly.react('turnover',[{x:s.date,y:s.turnover,type:'bar',marker:{color:'#2670b8'}}],layout('逐周双侧换手','日期','权重绝对变化之和'),config)}showFactor(rows[0].factor);
</script></body></html>'''
    output.write_text(html.replace('__PAYLOAD__', payload), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--factor-store',type=Path,default=Path('Data/factor_store'))
    parser.add_argument('--market',type=Path,default=Path('Data/raw/processed_data.parquet'))
    parser.add_argument('--output',type=Path,default=Path('Result/factor_reports/train_2020_2022'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    raw=pd.read_parquet(args.market,columns=['securityID','trade_dt','close','amt'])
    raw['trade_dt']=pd.to_datetime(raw['trade_dt'])
    raw=raw[(raw.trade_dt>=START)&(raw.trade_dt<=END)&(raw.trade_dt.dt.dayofweek<5)]
    if raw.duplicated(['trade_dt','securityID']).any():
        raise ValueError('行情日期与证券代码不唯一')
    close=raw.pivot(index='trade_dt',columns='securityID',values='close').sort_index()
    amount=raw.pivot(index='trade_dt',columns='securityID',values='amt').reindex_like(close)
    dates=close.index
    signals=dates.to_series().groupby(dates.to_period('W-FRI')).max().tolist()
    loc={d:i for i,d in enumerate(dates)}
    periods=[]
    for a,b in zip(signals[:-1],signals[1:]):
        if loc[b]+1<len(dates):
            periods.append((a,dates[loc[a]+1],dates[loc[b]+1]))
    paths=[(f,'Alpha158') for f in sorted((args.factor_store/'alpha158_values').glob('*.parquet'))]
    paths +=[(f,'GTJA191') for f in sorted((args.factor_store/'gtja191_values').glob('*.parquet'))]
    summary=[];weekly=[];issues=[]
    for i,(f,family) in enumerate(paths,1):
        row,w,err=report_factor(f,close,amount,periods,family)
        summary.append(row);weekly.append(w);issues.extend(err)
        if i%25==0 or i==len(paths): print(f'{i}/{len(paths)}',flush=True)
    s=pd.DataFrame(summary).sort_values(['family','factor'])
    w=pd.concat(weekly,ignore_index=True) if weekly else pd.DataFrame()
    e=pd.DataFrame(issues,columns=['factor','date','reason'])
    s.to_csv(args.output/'factor_summary.csv',index=False)
    w.to_csv(args.output/'factor_weekly.csv',index=False)
    e.to_csv(args.output/'factor_issues.csv',index=False)
    make_html(s,w,e,args.output/'factor_quality_report.html')
    print('Report:',(args.output/'factor_quality_report.html').resolve())


if __name__=='__main__': main()
