"""参照final/final_tree完整生成融合版图表和同结构报告。"""
from pathlib import Path
import json
import re
import subprocess
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from evaluation import metrics
from paths import RAW, CODE, REFERENCE

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
LABEL = dict(bl='BL组合', blrisk='风险约束BL', mv='MV组合', eq='等权组合',
             ind='MV+约束组合', blc='BL+约束组合')
COLORS = dict(zip(LABEL, ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b']))
INDICES = {'中证A500全收益指数.xlsx':'中证A500全收益', '上证综合全收益指数.xlsx':'上证综合全收益',
           '沪深300.xlsx':'沪深300全收益', '中证500.xlsx':'中证500全收益'}
FUNDS = {'广发.xlsx':'广发中证A500指增A','中金.xlsx':'中金中证A500指增A',
         '路迈博中证.xlsx':'路迈博中证A500指增A','天弘.xlsx':'天弘中证A500指增A','易方达.xlsx':'易方达中证A500指增A'}
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def fmt(c, value):
    if pd.isna(value): return '—'
    if isinstance(value, (str, int, np.integer)): return str(value)
    if '夏普' in c or '信息比率' in c: return f'{value:.2f}'
    if '换手' in c: return f'{value:.2f}x'
    return f'{value:.2%}'


def md(df):
    cols = df.columns.tolist()
    return '\n'.join(['| ' + ' | '.join(cols) + ' |', '|' + '|'.join(['---']*len(cols))+'|'] +
                     ['| '+' | '.join(fmt(c,r[c]) for c in cols)+' |' for _,r in df.iterrows()])


def image_table(df, title, filename, note='', width=None):
    cell = [df.columns.tolist()] + [[fmt(c,r[c]) for c in df.columns] for _,r in df.iterrows()]
    fig, ax = plt.subplots(figsize=(width or max(8, 1.55*len(df.columns)), .40*len(cell)+1.0))
    ax.axis('off')
    tab = ax.table(cellText=cell, bbox=[0,.035,1,.90], cellLoc='center')
    tab.auto_set_font_size(False); tab.set_fontsize(9); tab.scale(1,1.8)
    for (i,j), c in tab.get_celld().items():
        if i == 0:
            c.set_facecolor('#2f5597'); c.set_text_props(color='white', weight='bold')
        elif j == 0:
            c.set_facecolor('#f2f2f2'); c.set_text_props(weight='bold')
        elif i % 2 == 0: c.set_facecolor('#f7f9fc')
    ax.set_title(title, fontsize=12, weight='bold', pad=18)
    if note: fig.text(.025,.025,note,fontsize=9,va='bottom')
    fig.tight_layout(rect=[0,.06,1,.96]); fig.savefig(ROOT / filename,dpi=150,bbox_inches='tight'); plt.close(fig)


def peer_series():
    from backtest import load_index
    paths = [RAW/'中证A500全收益指数.xlsx'] + sorted((RAW/'其他指数或指增产品').glob('*.xlsx'))
    return {p.name: load_index(p) for p in paths}


def align(s, dates):
    # 保留网格之前最近的有效交易日，避免直接reindex后丢掉原始日频观测。
    return s.reindex(s.index.union(dates)).sort_index().ffill().reindex(dates)


def normalize_metrics(f):
    met = pd.read_csv(ROOT/'backtest_metrics_fusion.csv')
    for k,name in LABEL.items():
        turn = f[f'turn_{k}'].sum()*52/len(f)
        for prefix, scale in [('主动-',1),('指增产品-',.2)]:
            met.loc[met.组合.eq(prefix+name),'年化换手(单边)'] = scale*turn
    met.to_csv(ROOT/'backtest_metrics_fusion.csv',index=False,encoding='utf-8-sig')
    return met


def standard_charts():
    import runpy
    for name in ['render_metric_tables.py','cost_adjusted.py','render_monthly_win_plots.py','render_turnover_plot.py']:
        scope = runpy.run_path(str(CODE/'charts'/name))
        scope['main'].__globals__['ROOT'] = ROOT
        scope['main']()


def annual_tables(f, peers):
    dates = pd.DatetimeIndex(pd.to_datetime(f.end_date))
    starts = pd.DatetimeIndex(pd.to_datetime(f.w_date))
    data = {name:f[f'r_prod_net_{k}'].to_numpy() for k,name in LABEL.items()}
    data['中证A500全收益'] = f.r_idx.to_numpy()
    for file,name in INDICES.items():
        if name == '中证A500全收益': continue
        begin, end = align(peers[file],starts).to_numpy(), align(peers[file],dates).to_numpy()
        assert np.isfinite(begin).all() and np.isfinite(end).all()
        data[name] = end/begin-1
    records=[]
    for year in sorted(dates.year.unique()):
        mask=dates.year == year
        for name, returns in data.items():
            r=returns[mask]; m=metrics(r,f.r_idx.to_numpy()[mask])
            records.append({'年份':int(year),'名称':name,'年化收益率':m['年化收益'],
                            '年化波动率':m['年化波动'],'夏普比率':r.mean()/r.std()*np.sqrt(52),
                            '最大回撤':m['最大回撤'],'累计收益':m['累计收益'],'累计超额':m['累计超额'],
                            '周数':int(mask.sum()),'起算日':str(starts[mask][0].date()),'截至日':str(dates[mask][-1].date())})
    yearly=pd.DataFrame(records)
    yearly.to_csv(ROOT/'yearly_metrics_fusion.csv',index=False,encoding='utf-8-sig')
    for year,g in yearly.groupby('年份'):
        image_table(g[['名称','年化收益率','年化波动率','夏普比率','最大回撤']],
                    f'{year}年业绩评估（融合指增产品，已扣交易成本与管理费）',f'yearly_metrics_{year}_fusion.png',
                    '产品与指数使用同一周区间；保留每年首笔收益；年化52周。2026截至10-09。\n基金因可用起点不同，另按各自共同区间进行比较。',width=10)
    return yearly


def peer_charts(f, peers):
    dates=pd.DatetimeIndex([pd.Timestamp(f.w_date.iloc[0])]).append(pd.DatetimeIndex(pd.to_datetime(f.end_date)))
    products={LABEL[k]:np.r_[1,np.cumprod(1+f[f'r_prod_net_{k}'])] for k in ['ind','blc']}
    fig,ax=plt.subplots(figsize=(12,6)); rows=[]
    for file,name in INDICES.items():
        s=align(peers[file],dates); assert s.notna().all()
        normalized=s/s.iloc[0]
        ax.plot(dates,normalized,label=name,lw=2 if 'A500' in name else 1.2)
        rows.append({'名称':name,'累计收益':normalized.iloc[-1]-1})
    for name,v in products.items():
        ax.plot(dates,v,label='融合产品-'+name,lw=2.2); rows.append({'名称':'融合产品-'+name,'累计收益':v[-1]-1})
    ax.set_title('融合指增产品与全收益指数净值对比（同起点=1，产品已扣成本与管理费）')
    ax.legend();ax.grid(alpha=.3);fig.tight_layout();fig.savefig(ROOT/'peer_index_compare_fusion.png',dpi=150);plt.close(fig)
    pd.DataFrame(rows).to_csv(ROOT/'peer_index_metrics_fusion.csv',index=False,encoding='utf-8-sig')
    # 各基金使用其可用起点，产品与A500同起点重设为1，避免成立日不一致造成视觉误导。
    fig,axes=plt.subplots(2,3,figsize=(16,9)); fund_rows=[]; fund_weekly={}
    benchmark=np.r_[1,np.cumprod(1+f.r_idx)]
    for ax,(file,name) in zip(axes.flat,FUNDS.items()):
        s=align(peers[file],dates); valid=s.notna().to_numpy(); i0=np.flatnonzero(valid)[0]; ii=np.flatnonzero(valid)[-1]
        x=dates[i0:ii+1]; fund=s.iloc[i0:ii+1]/s.iloc[i0]
        ax.plot(x,fund,label=name,lw=1.6)
        ax.plot(x,benchmark[i0:ii+1]/benchmark[i0],label='A500全收益',color='black')
        for label,v in products.items(): ax.plot(x,v[i0:ii+1]/v[i0],label='融合'+label,lw=1.4)
        ax.set_title(name,fontsize=11);ax.grid(alpha=.3);ax.legend(fontsize=8);ax.tick_params(axis='x',rotation=25)
        fund_weekly[name]=s.pct_change(fill_method=None)
        fund_rows.append({'基金':name,'起算日':str(x[0].date()),'截至日':str(x[-1].date()),
                          '基金累计收益':fund.iloc[-1]-1,'融合MV约束同期收益':products[LABEL['ind']][ii]/products[LABEL['ind']][i0]-1,
                          '融合BL约束同期收益':products[LABEL['blc']][ii]/products[LABEL['blc']][i0]-1})
    axes.flat[-1].axis('off')
    axes.flat[-1].text(.03,.8,'比较口径\n\n每个子图中的基金、融合产品\n及A500全收益基准，均在该基金\n可用区间的共同起点归一为1。\n\n不同子图起算日不同，\n累计收益不宜跨子图直接比较。',va='top',fontsize=12)
    fig.suptitle('融合产品与A500指增基金同期净值对比（各自共同起点=1）',fontsize=14)
    fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(ROOT/'peer_fund_compare_fusion.png',dpi=150);plt.close(fig)
    pd.DataFrame(fund_rows).to_csv(ROOT/'peer_fund_metrics_fusion.csv',index=False,encoding='utf-8-sig')
    corr=pd.DataFrame(fund_weekly).corr()
    corr.to_csv(ROOT/'peer_fund_return_correlation.csv',encoding='utf-8-sig')
    return pd.DataFrame(rows)


def comparison_charts():
    comp=pd.read_csv(ROOT/'comparison_metrics.csv')
    comp['夏普比率']=np.nan
    frames={'线性':pd.read_csv(BASE/'final/backtest_weekly_external.csv'),
            '树模型':pd.read_csv(BASE/'final_tree/backtest_weekly_tree.csv'),
            '融合':pd.read_csv(ROOT/'backtest_weekly_fusion.csv')}
    for model,df in frames.items():
        for k,name in LABEL.items():
            r=df[f'r_prod_net_{k}'].to_numpy()
            comp.loc[comp.模型.eq(model)&comp.组合.eq(name.replace('+','＋').replace('组合','')),'夏普比率']=r.mean()/r.std()*np.sqrt(52)
    # 使用稳定键映射，避免展示标签差异影响六组合对照。
    names={'BL组合':'BL','风险约束BL':'风险约束BL','MV组合':'MV','等权组合':'等权','MV+约束组合':'MV＋约束','BL+约束组合':'BL＋约束'}
    ordered=[]
    for k,name in LABEL.items():
        for model,df in frames.items():
            row=comp[comp.模型.eq(model)&comp.组合.eq(names[name])].iloc[0].copy()
            r=df[f'r_prod_net_{k}'].to_numpy();row['夏普比率']=r.mean()/r.std()*np.sqrt(52)
            row['组合']=name;ordered.append(row)
    tab=pd.DataFrame(ordered)
    columns=['组合','模型','年化收益','年化波动','夏普比率','最大回撤','年化超额','跟踪误差','信息比率','周胜率','年化单边换手']
    image_table(tab[columns],'指增产品指标对比：线性模型、树模型与固定50/50融合（同窗口、已扣费）','comparison_metrics_table.png',
                '换手统一含首期建仓；融合版提高OSQP求解精度，其余组合设定沿用原版本。',width=19)
    tab[columns].to_csv(ROOT/'comparison_metrics_full.csv',index=False,encoding='utf-8-sig')
    for kind in ['excess','nav']:
        fig,axes=plt.subplots(1,2,figsize=(16,5),sharey=True)
        for ax,k in zip(axes,['ind','blc']):
            for model,df in frames.items():
                dates=pd.DatetimeIndex([pd.Timestamp(df.w_date.iloc[0])]).append(pd.DatetimeIndex(pd.to_datetime(df.end_date)))
                nav=np.r_[1,np.cumprod(1+df[f'r_prod_net_{k}'])]; benchmark=np.r_[1,np.cumprod(1+df.r_idx)]
                y=(nav/benchmark-1)*100 if kind=='excess' else nav
                ax.plot(dates,y,label=model+'模型-'+LABEL[k],lw=1.6)
            if kind=='nav':ax.plot(dates,benchmark,color='black',lw=2,label='A500全收益')
            else:ax.axhline(0,color='black',lw=.8)
            ax.set_title(LABEL[k]+'：'+('累计超额对比' if kind=='excess' else '产品净值对比'))
            ax.set_ylabel('累计超额（%）' if kind=='excess' else '净值');ax.grid(alpha=.3);ax.legend(fontsize=9)
        fig.suptitle('线性、树模型与50/50融合（产品已扣交易成本与管理费）')
        fig.tight_layout(rect=[0,0,1,.94])
        name='comparison_excess_ind_blc.png' if kind=='excess' else 'comparison_nav_prod_ind_blc.png'
        fig.savefig(ROOT/name,dpi=150);plt.close(fig)
    return tab


def inventory():
    files={}
    for folder,suffix in [('final','_external'),('final_tree','_tree')]:
        for path in sorted((REFERENCE/folder).glob('*.png')):
            target=path.name.replace(suffix,'_fusion')
            files.setdefault(target,[]).append(f'{folder}/{path.name}')
    rows=[{'参考图表':'；'.join(refs),'融合版图表':name,'已生成':(ROOT/name).exists()} for name,refs in files.items()]
    assert rows, '缺少冻结图表索引，不能生成空报告'
    assert all(row['已生成'] for row in rows), '参考目录图表未补齐'
    pd.DataFrame(rows).to_csv(ROOT/'chart_inventory.csv',index=False,encoding='utf-8-sig')
    return rows


def report(f,met,yearly,comparison,peer_metrics,charts):
    # 按原报告0—8章节顺序组织，优化及回测方法直接沿用原稿并修正已确认的口径描述。
    source=(BASE/'final/组合优化与回测报告.md').read_text(encoding='utf-8')
    methods=source[source.index('## 3. 三版组合优化'):source.index('## 5. 回测结果')]
    methods=methods.replace('_external','_fusion').replace('（周频调仓）','（周频调仓，固定50/50融合分数）')
    methods=methods.replace('2024-01-02 ~ 2026-10-09','2024-01-08 ~ 2026-10-09')
    methods=methods.replace('2024-01-15 ~ 2026-10-09','2024-01-08 ~ 2026-10-09（首个收益观测日为2024-01-15）')
    methods=methods.replace('与 v2 的**唯一区别**是预期收益的构造方式——',
                            '与v2相比，预期收益构造与协方差处理均有变化。预期收益方面，')
    methods=methods.replace('产品超额 = 0.2 × 主动超额','扣费前每周算术超额 = 0.2 × 主动组合每周算术超额；复合超额需根据净值另算')
    methods=methods.replace('按过去值，无前视','按过去值，无前视')
    methods=methods.replace('原因：周频分数噪声大，每周直接 top-30 平均要换 22 只股票；平滑后换手从 43.4x 降到 16.5x，且收益更高；',
                            '该平滑设定沿用既有方案，本次未重新选择窗口；')
    methods=methods.replace('（对全 A 股按行业加权求和并归一）','（按行业数据中的指数成分权重汇总并归一）')
    methods=methods.replace('Q = 预测分；','Q = 预测分 × σ_cs；')
    methods=methods.replace('便于与 v2 对比"BL 后验 vs 直接 α"的差异。',
                            '但因协方差处理也有区别，两者对比不能单独归因于BL后验。')
    methods=methods.replace('（与回测的换手口径完全一致）','（同一候选池股票的漂移权重与回测一致；被移出候选池的强制卖出不在优化变量中）')
    methods+='\n本次仅将OSQP绝对/相对容差设为1e-9、启用polishing，持仓边界按1e-7数值容差校验。行业中性为软惩罚，并非严格中性或跟踪误差硬上限。\n\n'
    cols=['组合','累计收益','年化收益','年化波动','最大回撤','夏普比率','年化超额','跟踪误差(年化)','信息比率','周胜率','年化换手(单边)']
    active=met[met.组合.str.startswith('主动-')].copy();active['组合']=active.组合.str.replace('主动-','',regex=False)
    product=met[met.组合.str.startswith('指增产品-')].copy();product['组合']=product.组合.str.replace('指增产品-','',regex=False)
    bench=met[met.组合.eq('中证A500全收益指数')]
    cost=pd.read_csv(ROOT/'backtest_metrics_net_fusion.csv')
    costshort=cost[['组合','年化超额(毛)','年化超额(扣交易)','年化超额(扣交易+管理费)']]
    pivot=yearly.pivot(index='名称',columns='年份',values='年化收益率').reindex(list(LABEL.values())+list(INDICES.values()))
    pivot.columns=[f'{c}年化收益' for c in pivot.columns];pivot=pivot.reset_index()
    monthly=pd.read_csv(ROOT/'monthly_excess.csv'); monthly=monthly[monthly.模型.eq('融合')]
    winrows=[]
    display={'BL':'BL组合','风险约束BL':'风险约束BL','MV':'MV组合','等权':'等权组合','MV＋约束':'MV+约束组合','BL＋约束':'BL+约束组合'}
    for name,g in monthly.groupby('组合',sort=False):
        row={'组合':display[name]}
        for year in [2024,2025,2026]:
            sub=g[g.月份.str.startswith(str(year))];row[str(year)]=f'{int(sub.跑赢.sum())}/{len(sub)}'
        row['合计']=f'{int(g.跑赢.sum())}/{len(g)}';winrows.append(row)
    def embeds(names): return '\n\n'.join(f'![{name.removesuffix(".png")}]({name})' for name in names)
    metadata=json.loads((ROOT/'run_manifest.json').read_text(encoding='utf-8'))
    report=f'''# 双模型融合分数版：组合优化与回测报告

> 本报告记录将线性模型（Ridge）与树模型（LightGBM）的截面排名分各按50%融合，再接入既有组合优化与回测管线的全部步骤。报告结构与图表样式参照`final/`和`final_tree/`。所有本次产物位于`final_fusion/`。

---

## 0. 总体流程

```text
final/predictions_external.parquet + final_tree/predictions_tree.parquet
        │ run_pipeline.py：按周×股票校验、信号日一致性校验、防前视校验
        ▼
融合分数 = 50%线性排名分 + 50%树模型排名分（平均后不重新排名）
        ▼
predictions_fusion.parquet（133周×500只）
        ├─ portfolio_opt_v1_fusion.py → BL / 风险约束BL / MV / 等权
        ├─ portfolio_opt_v2_fusion.py → MV+约束
        └─ portfolio_opt_v3_fusion.py → BL+约束
        ▼
backtest_fusion.py → evaluate_fusion.py → render_all_artifacts.py
        ▼
净值与超额图、主动/产品指标表、费用分层、月度胜率、换手、年度表、同业与三模型对比
```

## 1. 输入数据

| 项目 | 内容 |
|---|---|
| 线性分数 | `final/predictions_external.parquet`，Corr 0.50因子筛选＋Ridge模型的对齐排名分 |
| 树模型分数 | `final_tree/predictions_tree.parquet`，LightGBM Huber、clipped_relative标签的对齐排名分 |
| 融合方式 | 固定50/50，按`pred_week, securityID`一一对应；不填补缺失、不重新排名 |
| 行数与覆盖 | {metadata['rows']:,}行，{metadata['weeks']}周×{metadata['securities']}只，第196—328周 |
| 行情与行业 | 原项目`processed_data.parquet`及申万一级行业权重；行业数据自2024-09-23起可用 |
| 基准与同业 | 中证A500全收益、上证综合全收益、沪深300全收益、中证500全收益；五只基金净值仅用于待复核图 |

## 2. 预测分数准备（run_pipeline.py）

沿用原始分数准备的5交易日块编号：信号位于面板索引i时，最早用于第`i//5+2`周；第T周信息截止日为`(T−1)×5−1`。
对两模型的每个周股票键做外连接并要求全部匹配；检查信号日相同、分数在[0,1]且无缺失，再逐行平均。
对融合信号逐行核验`feature_dt ≤ 信息截止日`。`fusion_signal_audit.parquet`保留两侧分数与融合值，输入哈希记录于`run_manifest.json`。

本次重新选股、求解持仓、计算收益及漂移换手；不是把原有净收益序列平均。基础预测模型未重新训练，50/50比例未根据本窗口选优。

{methods}
## 5. 回测结果（133周，产品80/20口径）

### 5.1 主动组合指标（已扣交易成本0.15%）

{md(pd.concat([bench,active])[cols])}

{embeds(['metrics_table_active_fusion.png','nav_curves_fusion.png','excess_curves_active_fusion.png'])}

### 5.2 指增产品指标（已扣交易成本与管理费，正式汇报口径）

{md(pd.concat([bench,product])[cols])}

融合BL+约束产品年化超额5.64%、信息比率1.15；融合MV+约束年化超额5.54%、信息比率1.19、年化单边换手3.27倍。
两者收益接近，MV+约束的主动风险效率与换手更优，BL+约束的最大回撤略浅。其余四种组合保留作方法对照。

{embeds(['metrics_table_product_fusion.png','nav_curves_product_fusion.png','excess_curves_fusion.png'])}

### 5.3 扣成本费用前后对比（产品年化超额）

{md(costshort)}

{embeds(['metrics_table_product_net_fusion.png'])}

### 5.4 分年度业绩（产品与指数同窗口，年化收益）

{md(pivot)}

年度直接复合该年所有已有周收益，保留每年第一笔收益；跨年周按期末日期归属。指数按相同周起止日取收益并使用52周年化。
这修正了原年度脚本先截取净值再pct_change漏掉年首收益、以及产品与指数起点不同的问题，因此年度数字不能直接与原目录年度表混用。
完整年度表同时列出年化波动、夏普、最大回撤。2026截至10-09；首末年度不完整。

{embeds([f'yearly_metrics_{year}_fusion.png' for year in [2024,2025,2026]])}

### 5.5 同业对比

{md(peer_metrics)}

指数与两种融合产品从2024-01-08同一起点归一为1，产品净值已扣费，指数未额外扣费。
基金图分别将每只基金、两种产品和A500基准在该基金可用区间的共同起点归一为1。五只基金的起算日不同，因此只在各自子图内进行同期累计收益比较。

{embeds(['peer_index_compare_fusion.png','peer_fund_compare_fusion.png'])}

### 5.6 月度超额胜率（指增产品vs中证A500全收益）

{md(pd.DataFrame(winrows))}

按周收益期末所属月份复合，与原月度图保持一致；首末月及跨月周不是精确自然月日频收益。

{embeds([f'monthly_win_{k}_fusion.png' for k in LABEL])}

### 5.7 年化换手率（产品口径=0.2×主动口径）

{md(product[['组合','年化换手(单边)']])}

本报告统一将首期建仓计入换手并按`Σturn×52/n`年化。旧目录指标文件排除首期并按n−1年化，有小幅差异。

{embeds(['turnover_by_combo_fusion.png'])}

## 6. 与线性、树模型分数版对比（同窗口、同口径）

{md(comparison[['组合','模型','年化收益','最大回撤','年化超额','跟踪误差','信息比率','年化单边换手']])}

融合BL+约束年化超额由线性版4.54%提高至5.64%，IR由1.04提高至1.15；融合MV+约束的IR达到1.19，高于对应的线性/树模型方案。
这种改善来自融合后重新选股和统一优化，不能用原组合净值混合的结果替代解释；现有实验尚不能单独识别每一优化环节的贡献。

{embeds(['comparison_metrics_table.png','comparison_excess_ind_blc.png','comparison_nav_prod_ind_blc.png'])}

## 7. 结论、数据质量与限制

- 最终产品选用固定50/50融合的MV＋行业软惩罚＋换手惩罚组合；融合BL约束作为对照。MV约束的信息比率更高、换手更低、年化超额接近，且实现环节更少。此为综合研究结果形成的产品设计决定，尚需后续独立窗口验证，不等同于事先指定MV后的独立测试。
- 从本次产品结果看，MV+约束值得成为下一阶段优先验证候选，但不能事后把最高指标当作预先选定策略的成绩。
- 全期改善不等于每阶段占优：2026融合BL+约束累计超额约0.41%，低于两套单模型的对应值。年度同窗口统计见CSV。
- 固定500只股票池存在幸存者偏差；未复权价格可能扭曲标签与持仓收益；未模拟停牌、涨跌停和实际成交容量。
- 行业仅采用偏离软惩罚，自2024-09-23起生效；产品没有严格行业中性或跟踪误差硬约束。
- 五只基金按各自可用起点与产品、A500基准同期归一化比较；不同基金区间、策略、费率与风险暴露不完全相同。
- 单边成本0.15%和年管理费0.5%沿用原设定；被动复制成本、托管费及额外仓位再平衡成本未单列。首期建仓采用原回测0.5×权重和定义。
- 基础模型已经过研究筛选，本窗口仍是研究评价；融合比例虽固定，也不构成新的独立样本外验证。

## 8. 文件与复现清单

| 脚本 | 功能 | 主要输出 |
|---|---|---|
| `Code/run.py` | 一键执行/重训树模型/重绘 | 全部结果与日志 |
| `Code/signals.py` | 对齐两模型、固定50/50平均 | 三套分数与融合审计 |
| `Code/portfolio_basic.py` | BL、风险BL、MV、等权 | v1权重 |
| `Code/portfolio_mv.py` / `Code/portfolio_bl.py` | 带行业与换手惩罚的MV/BL | v2/v3权重和行业偏离 |
| `Code/backtest.py` / `Code/evaluation.py` | 回测和独立计算核验 | 周收益、对比及校验 |
| `Code/visualization.py` / `Code/charts/` | 原样式图表与报告 | 22张图及报告 |

完整对应原目录的图表共{len(charts)}张；历史概览图见reference目录，见`chart_inventory.csv`逐一对应清单。
在提交目录运行：`python Code/run.py`。仅更新本提交包Result/reproduced。
如需重绘图表和报告：`python Code/run.py --charts-only`。

全部持仓、收益、漂移换手及扣费已独立核验，见`validation_results.json`。
'''
    (ROOT/'融合产品组合优化与回测报告.md').write_text(report,encoding='utf-8')
    (ROOT/'图表清单.md').write_text('# 融合版与原目录图表对应清单\n\n'+md(pd.DataFrame(charts).drop(columns='已生成'))+'\n',encoding='utf-8')
    references=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',report)
    assert len(references)==len(charts) and all((ROOT/p).exists() for p in references)
    print(f'完成：{len(charts)}张参考对应图表；报告已嵌入全部对应图表。')


def main():
    f=pd.read_csv(ROOT/'backtest_weekly_fusion.csv')
    met=normalize_metrics(f)
    standard_charts()
    peers=peer_series()
    yearly=annual_tables(f,peers)
    peer_metrics=peer_charts(f,peers)
    comparison=comparison_charts()
    charts=inventory()
    report(f,met,yearly,comparison,peer_metrics,charts)


if __name__=='__main__':
    main()
