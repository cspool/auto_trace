#!/usr/bin/env python3
"""Write separate evidence-grounded latency and resource reports with SVG examples."""
from pathlib import Path
import argparse,base64,hashlib,html,json,re
from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

def table(headers,rows):return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in rows)
def ms(n):return f'{n/1e6:.3f}'
def sec(n):return f'{n/1e9:.3f}'
def figure(name,caption,distribution=False):return f'<figure class="report-figure{" distribution-page" if distribution else ""}"><img src="../figures/{name}.svg" alt="{html.escape(caption)}"><figcaption>{caption} <a href="../figures/{name}.svg">SVG</a> · <a href="../figures/{name}.png">PNG</a></figcaption></figure>\n\n'
def paired_figures(key,number,windows):
 w=windows[key];lo,hi=w['view'];common=f"同一原始窗口 {lo/1e9:.9f}–{hi/1e9:.9f} s（相对trace原点），跨度 {w['duration_ns']/1e6:.3f} ms。两图宽度、横轴起点、线性比例尺和刻度完全相同。"
 a=f"图{number}A · Process时间分布。"+common+"显示这个窗口内全部可见的入选堆，保留全局排名；每堆仅一个矩形，左右边界标识其起止范围（按视窗裁切），不表示连续执行；源实例时长未被改写。"
 b=f"图{number}B · 与A图同窗的资源指标。"+common+"资源实例ID可在A图逐一对应。高度按指标数值缩放；SE是R07观测，带*项是R08重放或L2投影，不能合并为同次资源竞争结论。"
 return figure(key+'_high',a)+figure(key+'_resource',b)
def ns_stats(x,field):return ms(x[field]) if x.get('n') else '—'
def med(x):return f"{x['median']:.2f}（n={x['n']}）" if x.get('n') else '未覆盖'
def span_sources(f):return f"{f['process_count']:,} 个 Process；{f['kernel_count']:,} 个唯一严格归属 kernel；Process 时间跨度 {sec(f['source_process_extent_ns'])} s。"
def per_process_report(facts,items):
 text="# 高延迟Process时间分布总览\n\n本册作为并发与资源分析的定位参考。每个超过总延迟10%的Process包含五堆矩形总览和一张最长区间矩形放大图。矩形边界标识该堆最早开始、最晚结束，跨度含间隙，不等于累计执行时长。成员明细保留在数据文件，图内不绘制成员线。\n\n"
 text+="阈值分母为各trace全部Process实例时长之和，包含并发和父/fragment嵌套，不是E2E wall time。单batch覆盖29次forward；Batch8覆盖8请求的首个prefill/decode，不能推断全部生成步。总览横轴采用公共折叠映射；放大图采用线性真实时间轴。原始时间与排序不变。先选累计时长最高的堆，再选该堆单次时长最高的实例；放大图仅绘制选中最长实例的一个矩形，两侧各留5%空白。\n\n"
 text+=table(['Trace','Process','实例数','累计 / s','占全部时长'],[[x['trace'],x['type'],x['instance_count'],sec(next(g for g in facts[x['trace']]['groups'] if g['name']==x['type'])['duration_ns']['sum']),f"{x['share']:.2%}"] for x in items])
 text+="\n重点阅读[并发与资源报告](../concurrency/REPORT.html)：有/无同设备kernel重叠、同窗资源分布及调度验证条件。Batch8 MLP包含1024个父过程和3072个fragment，混合中位数不能代表完整MLP耗时。没有before/after实验，不报告加速比。\n\n"
 text+="完整统计、各phase与fragment分布及十段交集校验见[统计数据](../data/SUMMARY.json)与[分段CSV](../data/SEGMENTS.csv)。\n"
 for item in items:
  key,name=item['trace'],item['type'];g=next(g for g in facts[key]['groups'] if g['name']==name);st=g['duration_ns'];label='单 batch' if key=='single_batch' else 'Batch8'
  caption=f"{label} / {name}：累计 {sec(st['sum'])} s，占全部Process时长和 {g['share_pct']:.2f}%；五堆按累计时长排序，{st['n']}个成员仅用于统计，不在矩形内部展开。矩形左右边界标识最早开始和最晚结束，不代表一条连续执行区间。中位 {ms(st['median'])} ms，P95 {ms(st['p95'])} ms。"
  panel=figure(item['full'],caption,True).replace('<figure ',f'<figure id="process_{key}_{name}" ',1)
  text+=panel
  text+=figure(item['detail'],f"{label} / {name}：累计延迟最高的堆{item['selected_pile']}，最长实例 {item['focus_duration_ns']/1e6:.6f} ms，原始相对区间 [{item['focus_begin_ns']/1e9:.9f}, {item['focus_end_ns']/1e9:.9f}) s。图中只有目标实例的一个矩形，左右边界表示其真实起止。采用线性放大，精确ID见SVG提示及PROCESS_DISTRIBUTIONS.json。")
 return text

def main(root,repo,only_high=False):
 out=root/'analysis_reports';facts=json.loads((out/'data/SUMMARY.json').read_text());s=facts['single_batch'];b=facts['batch8'];sg={g['name']:g for g in s['groups']};bg={g['name']:g for g in b['groups']};fg={k:json.loads((out/'figures'/f'{k}_high.json').read_text()) for k in facts};windows=json.loads((out/'figures/PAIRED_WINDOWS.json').read_text())
 resource='''# 资源瓶颈与调度机会报告

**结论：现有资源证据可用于定位GDN与RMSNorm的读写/L2特征，但不足以给MLP定性瓶颈，也不足以证明增加并发就能提速。**

资源时间线不是另一份全过程图。它只显示成功关联硬件指标的窗口，原始堆排名保留；`»`跳过无数据时段不等于GPU空闲。下文分别讨论覆盖、指标含义、真实kernel重叠和待验证机会。

## 1. 先看覆盖率，再解释颜色和高度

'''
 resource+=table(['来源','入选Process实例','可显示硬件资源实例','覆盖率','资源图可见堆'],[['单 batch',s['selected_count'],s['hardware_eligible_instances'],f"{s['hardware_eligible_instances']/s['selected_count']*100:.2f}%",7],['Batch8',b['selected_count'],b['hardware_eligible_instances'],f"{b['hardware_eligible_instances']/b['selected_count']*100:.2f}%",9]])
 resource+='''
单 batch 的Process trace覆盖完整请求中的29次forward，但L2硬件样本只关联少量实例；Batch8是8请求首个prefill/decode的Process样例，硬件计数仍为有界子集。资源图不出现某个Process，意味着缺少可显示硬件证据，不能解释为它没有消耗资源。

'''
 resource+=table(['Batch8 Process','总实例','SE均值有效','读参考有效','写参考有效','L2指标有效'],[[name,r['instances'],r['compute_pct']['n'],r['read_reference_pct']['n'],r['write_reference_pct']['n'],r['l2_hit_pct']['n']] for name,r in b['resources'].items()])
 resource+='''
MLP是高延迟分析的重要对象，却没有对应的读写/L2重放覆盖。其3072个短fragment也没有有效SE窗口均值。资源图默认隐藏这些空白，是显示策略，不是排除它们的优化价值。短窗口的ε仍代表未知，不是测得的极低占用率。

## 2. 单 batch：L2投影值支持样例检查，不能给整类Process定性

'''
 resource+=table(['Process','关联实例','family样本数','投影L2范围 / GB/s'],[[name,r['l2_instances'],r['l2_sample_count'],f"{r['l2_projected_GBps']['min']:.2f}–{r['l2_projected_GBps']['max']:.2f}" if r['l2_sample_count'] else '未覆盖'] for name,r in s['resources'].items()])
 resource+='''
这些是原报告的 `projected_L2_throughput_GBps_on_R07_latency_axis` 字段，使用了重放流量与R07投影口径。不同family不能直接合并成一个Process的实测带宽。未取得可验证的L2峰值，因此报告保持GB/s，不把HBM的1206 GB/s用作L2分母，也不把命中率当利用率。

'''
 resource+=paired_figures('single_batch',1,windows)
 resource+='''## 3. Batch8：重放资源分布与可用性边界

读、写分别采用同条PMC记录的字节数与EndNs−BeginNs计算，再除以文档实测参考1206 GB/s。不同计数模式是不同重放，不能把读写百分比相加，或代入R07 Process时长重新计算。

'''
 resource+=table(['Process','读参考P50 / %','写参考P50 / %','L2命中P50 / %','L2请求P50 / Greq/s'],[[name,med(r['read_reference_pct']),med(r['write_reference_pct']),med(r['l2_hit_pct']),med(r['l2_Greqps'])] for name,r in b['resources'].items()])
 resource+='''
上表是各指标有效Process参考值的**非加权中位数**，每列标注自己的样本数。尤其RMSNorm的读/L2与写覆盖数不同，这些列不是配对实验。GDN与RMSNorm呈现不同的L2命中/请求模式，可用于选择后续访存检查对象；命中率差异本身不能证明某个算子已达到L2带宽上限。

'''
 resource+=paired_figures('batch8',2,windows)
 ratios=b['replay_vs_observed_kernel_duration_ratio']
 resource+=f'''
重放耗时与关联R07 kernel耗时并不恒等：形状匹配记录中，读模式比值P95约 **{ratios['read']['p95']:.2f}**，写模式约 **{ratios['write']['p95']:.2f}**。这进一步说明，较低的重放带宽参考百分比不能直接转化为“正常服务还剩多少带宽可供并发”。这些比值仅用于说明测量环境差异，不用于重算原始延迟。

## 4. 计算指标的零值：先处理解释限制

Batch8 保留的 **2,491,806 条 SE 采样值全部为0**；入选类型中2807个可用窗口均值也全部为0。这是源数据事实，不是本报告补零。它在本数据集中没有区分不同窗口的能力，不能据此宣布GPU计算空闲、算力仅使用0%，或放心叠加计算任务。

资源报告应把它列为需要进一步检查的信号语义/采样链路问题。现有R08指标与R07 SE不是同一次采集，不能用R08数值替换这些零值。当前可讨论的主要是**重放读写/L2特征与覆盖范围**，而非实测计算吞吐饱和度。

## 5. 原始 kernel 并发证据有多强

以下结果由R07唯一严格归属kernel的实际起止端点独立扫描，并与原并发表核对；不使用资源图折叠后的坐标：

'''
 resource+=table(['来源 / 设备','唯一kernel数','kernel时长和 / s','busy并集 / s','并发≥2并集 / µs','峰值'],[[f"{label} / DCU{dev}",x['unique_kernels'],sec(x['kernel_duration_sum_ns']),sec(x['busy_union_ns']),f"{x['overlap_union_ns']/1e3:.3f}",x['peak']] for label,f in [('单 batch',s),('Batch8',b)] for dev,x in f['devices'].items()])
 resource+='''
虽然峰值都达到2，重叠并集只有微秒或亚微秒量级。**峰值为2不等于存在显著的并发吞吐收益。** 这些是所选、已归属kernel的统计，不是全设备活动普查；未trace或未归属的区间不能称为空闲。跨设备显示坐标也没有被用来证明精确同步。

源码快照的默认DP选卡逻辑使用 `4×waiting + running`，在最小分数的engine间按既定遍历顺序选择；显式指定rank的请求走指定设备。当前trace的请求分布只能说明这组请求怎样执行，不能证明某种4+4分配普遍最优，更不能说明现有调度器已经根据本报告的资源指标在线决策。

## 6. 候选方向与验证条件

'''
 resource+=table(['候选方向','已有支持','仍缺的关键证据','验证应关注'],[
 ['GDN / RMSNorm访存优化','存在形状匹配的读写/L2重放参考','L2峰值、完整访存路径、正常运行影响','选定kernel的源码/launch、同输入kernel与E2E对照'],
 ['MLP算子优化','高延迟报告与owned-kernel成本都表明值得检查','当前没有MLP读写/L2硬件覆盖','先补足对应证据，再区分矩阵乘、激活和调度成本'],
 ['资源互补的请求/算子调度','当前图可定位有资源证据的窗口','依赖、队列可执行性、显存共存、同次资源与跨卡时钟边界','正确性、TTFT/TPOT、吞吐、显存和尾延迟'],
 ['计算采样指标核验','Batch8原始SE序列全0且kernel确有执行','指标语义与采样链路的独立核对','不把0或ε作为可用计算余量的依据']])
 resource+='''
线性注意力层存在 `QKV → GDN → 输出投影 → MLP` 的数据依赖。不同颜色的资源条不能授权打破这些依赖，也不能把层间串行直接认定为可优化缺陷。可行的调度机会须在依赖、队列、资源共存和实际指标改善共同成立后，才能升级为已验证优化。

本报告没有启动上述实验；这些是后续验证任务，不是已实现收益。

## 7. 查看原始窗口与计算结果

- [单 batch资源图](../../revised/single_batch/CONCURRENCY_UTILIZATION.html) · [Batch8资源图](../../revised/batch8/CONCURRENCY_UTILIZATION.html)
- [Batch8带宽公式、覆盖率与独立审计](../../batch8_bandwidth/README.md) · [L2计数](../../batch8_bandwidth/L2_README.md)
- [单 batch L2样本与投影口径](../../single_batch_bandwidth/L2_README.md)
- [完整统计与精确实例ID](../data/SUMMARY.json) · [图例坐标与哈希](../figures/FIGURE_MANIFEST.json) · [成对窗口起止与实例ID](../figures/PAIRED_WINDOWS.json)
- [调度源码快照](../sources/core_client.py)：`get_core_engine_for_request`；[固定输入FX结构参考](../sources/fx_process_reconstruction.md)。来源哈希列在报告manifest中。
'''
 items=json.loads((out/'figures/PROCESS_DISTRIBUTIONS.json').read_text());cases=json.loads((out/'figures/CONCURRENCY_CASES.json').read_text())
 high=per_process_report(facts,items)
 resource+='\n## 8. 按实际kernel重叠分类选取窗口\n\n并发判据是同设备R07严格归属kernel在时间上的重叠，不能用父子Process嵌套或跨设备对齐直接替代。图1A/B与图2A/B已经检查为无同卡kernel重叠窗口，且含有可用资源参考。\n\n'
 resource+=table(['trace','情况','设备','区间内峰值','≥2重叠 / µs','资源证据'],[[label,'有同卡kernel重叠',c['with_overlap']['device'],c['with_overlap']['peak'],f"{c['with_overlap']['overlap_ns']/1e3:.3f}",'没有匹配计数，不补零'] for key,label in [('single_batch','单 batch'),('batch8','Batch8')] for c in [cases[key]]]+[[label,'无同卡kernel重叠','/'.join(x['device'] for x in c['without_overlap']['per_instance_device_check']),max(x['peak'] for x in c['without_overlap']['per_instance_device_check']),'0.000','显示同窗资源参考'] for key,label in [('single_batch','单 batch'),('batch8','Batch8')] for c in [cases[key]]])
 resource+='\n有并发但没有匹配硬件证据的窗口，只能报告执行重叠，不能报告其资源使用率。当前不为制作图片重新采集；无并发且有硬件数据的窗口承担资源读图示例。[窗口分类与kernel证据](../figures/CONCURRENCY_CASES.json)。\n'
 for key,label in [('single_batch','单 batch'),('batch8','Batch8')]:resource+=figure(key+'_kernel_overlap',f'{label}：已观测的有kernel重叠窗口。原始kernel条形真实相交，资源计数不覆盖这些实例，因此没有对应资源占用率图；不能以别的Process或重放数据填补。完整kernel名称、ID和分类区间见CONCURRENCY_CASES.json。')

 # Put actual concurrency first, followed by matched resource windows and interpretation.
 sections=re.split(r'(?m)^## ',resource)
 lead=sections[0].replace('资源瓶颈与调度机会报告','并发执行与资源占用分析报告')
 order=[5,8,2,3,1,4,6,7]
 resource=lead
 for number,old in enumerate(order,1):
  section=next(x for x in sections[1:] if x.startswith(str(old)+'. '))
  resource+='## '+re.sub(r'^\d+\. ',str(number)+'. ',section)
 resource=resource.replace('下文分别讨论覆盖、指标含义、真实kernel重叠和待验证机会。','正文首先检查实际kernel并发及有/无重叠窗口，再对照同窗资源指标，最后讨论证据覆盖与调度验证条件。')

 extra=json.loads((out/'figures/SEGMENT_PAIRED_WINDOWS.json').read_text())
 inventory=json.loads((out/'data/ALL_KERNEL_OVERLAPS.json').read_text())
 resource+='\n## 9. 扩展检查：全部已观测kernel重叠区间\n\n按同设备实际kernel重叠连续区间逐一检查，不只选最长事件。下表完整列出归档中的重叠区间；同一窗口多个kernel交叠的时长按并集计数。\n\n'
 resource+=table(['Trace','序号 / 设备','相对起点 / s','相对终点 / s','重叠 / µs','峰值','匹配资源kernel'],[[key,f"{i} / D{r['device']}",f"{r['begin_ns']/1e9:.9f}",f"{r['end_ns']/1e9:.9f}",f"{r['overlap_ns']/1e3:.3f}",r['peak'],r['matched_resource_kernels']] for key,v in inventory.items() for i,r in enumerate(v['segments'],1)])
 resource+='\n全部重叠区间仍未匹配到有效资源计数，因此当前可确认执行重叠，不能量化这些交叠瞬间的计算/带宽竞争。扩大归档窗口选择不会产生缺失的测量值。[全部kernel ID与时间戳](../data/ALL_KERNEL_OVERLAPS.json)。\n\n'
 resource+='## 10. 跨时间段的资源与执行对照\n\n从原始十段分别选择有硬件证据的时间段：单batch第1、2、3、6段；Batch8第1、3、5、6、8段。每段按开始时间排序，选取居中的两个完整硬件实例（不足两个则取全部），使用其区间并集加两侧5%留白；不按利用率高低挑选。两图使用完全相同的真实窗口和线性刻度。这些是已有归档的新增检查窗口，不是新运行采集。\n\n'
 from expand_process_and_concurrency_examples import read
 native={key:read(root/'revised'/key/'CONCURRENCY_UTILIZATION.html') for key in facts}
 window_rows=[]
 for stem,w in extra.items():
  d=native[w['trace']];lo,hi=w['view'];data=json.loads((out/'figures'/(stem+'_resource.json')).read_text());checks=[]
  for dev in sorted({r['device'] for r in data['instances']}):
   cs=[x for x in d['counts'] if x[3]=='kernel' and x[2]==dev and x[0]<hi and x[1]>lo]
   checks.append({'device':dev,'peak':max([x[4] for x in cs] or [0]),'overlap_ns':sum(min(hi,x[1])-max(lo,x[0]) for x in cs if x[4]>1)})
  w['kernel_checks']=checks;window_rows.append([w['trace'],w['section']+1,f"{lo/1e9:.6f}–{hi/1e9:.6f}",f"{(hi-lo)/1e6:.3f}",len(data['instances']),'/'.join(f"D{x['device']}:{x['peak']}" for x in checks),f"{sum(x['overlap_ns'] for x in checks)/1e3:.3f}"])
 resource+=table(['Trace','原始段','原始窗口 / s','跨度 / ms','资源实例','同卡峰值','重叠 / µs'],window_rows)
 metrics={}
 for stem,w in extra.items():
  data=json.loads((out/'figures'/(stem+'_resource.json')).read_text())
  for r in data['instances']:
   for glyph in r['glyphs']:
    if glyph['value'] is None:continue
    group=(w['trace'],r['name'],glyph['label'],glyph['unit']);metrics.setdefault(group,[]).append(glyph['value'])
 resource+='\n### 跨窗口比较\n\n以下范围仅来自本次分段窗口的有效实例，属于案例比较，不是全体Process的分布估计；重复使用原有窗口不会当成新采集样本。\n\n'
 resource+=table(['Trace / Process','指标','有效实例','最小–最大'],[[f'{key} / {name}',metric,len(values),f'{min(values):.2f}–{max(values):.2f} {unit}'] for (key,name,metric,unit),values in metrics.items()])
 resource+='\n单batch样例同时包含prefill与decode，L2投影值随Process及窗口变化，不能把某个高值归因为并发竞争。Batch8各窗口SE仍为0，未提供可区分的计算利用率证据；GDN与RMSNorm的读写/L2特征可用于选择访存优化对象。各列有不同的有效记录数，缺失写计数的窗口不能补零或与其他窗口的写计数拼接。\n\n'
 resource+='\n新增窗口用于比较不同时间段的执行与资源属性；不能从少数窗口外推整段平均占用率或吞吐收益。未覆盖的原始分段仍保留在附表，未作为零占用样本。\n'
 for index,(stem,w) in enumerate(extra.items(),3):
  data=json.loads((out/'figures'/(stem+'_resource.json')).read_text());label=f"{w['trace']} · 原始第{w['section']+1}段";peak=max(x['peak'] for x in w['kernel_checks']);ol=sum(x['overlap_ns'] for x in w['kernel_checks'])
  resource+=f"\n### {label}\n\n窗口内已归属kernel同设备峰值为{peak}，重叠并集合计 {ol/1e3:.3f} µs。资源与Process区间逐实例对齐；Host窗口包含的计数参考不能当作每个瞬间的全卡利用率。\n\n"
  resource+=table(['Process / 设备 / phase','指标','数值','测量口径'],[[f"{r['name']} / D{r['device']} / {r['phase']}",g['label'],'未覆盖' if g['value'] is None else f"{g['value']:.2f} {g['unit']}",'R08重放/投影' if g.get('replay') else 'R07窗口观测'] for r in data['instances'] for g in r['glyphs']])
  resource+=paired_figures(stem,index,extra)
 (out/'data/EXPANDED_WINDOW_ANALYSIS.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2)+'\n')

 sources=out/'sources';sources.mkdir(exist_ok=True)
 import shutil
 shutil.copy2(root/'batch8_report/site/source_snapshot/vllm/v1/engine/core_client.py',sources/'core_client.py')
 shutil.copy2(repo/'workload_profile/fx/traces/20260729T050800Z-fx-89687ae2-R032-qwen35-27b-eager-row0-hcu0/input1_layer0/fx_process_reconstruction.md',sources/'fx_process_reconstruction.md')
 aliases={'gdn_recurrent_core':'GDN','qkv_projection':'QKV','mlp':'MLP','post_attention_rmsnorm':'Post-RMS'}
 resource+='\n## 附表：逐段核查硬件覆盖与原始kernel重叠\n\n沿用高延迟报告的十个原始区间，包括没有硬件样本的区间，不因资源图隐藏空白而删除分母。busy和重叠来自各设备原始kernel扫描；超出Process最外端点的异步kernel尾部另行保留，不强行凑入本表。\n\n'
 resource+=table(['trace','段','硬件/相交实例','DCU0 busy / ms','DCU1 busy / ms','≥2重叠 / µs (D0/D1)'],[[label,row['segment'],f"{row['hardware_intersecting_instances']}/{row['intersecting_selected_instances']}",ms(row['per_device']['0']['busy_ns']) if '0' in row['per_device'] else '—',ms(row['per_device']['1']['busy_ns']),'/'.join(f"{row['per_device'][dev]['overlap_ns']/1e3:.3f}" if dev in row['per_device'] else '—' for dev in ['0','1'])] for label,f in [('单',s),('B8',b)] for row in f['time_segments']])
 resource+='\n0/0表示本段没有入选Process记录；busy=0仅表示该采集集合没有kernel区间，不代表GPU空闲。这张表用于发现覆盖偏差和选择进一步检查的区间，不是逐段计算空闲资源容量的表。[分段CSV](../data/SEGMENTS.csv)。\n'
 docs={'concurrency':('并发执行与资源占用分析报告',resource),'high_latency':('高延迟Process时间分布总览',high)}
 if only_high:docs={'high_latency':docs['high_latency']}
 css='''body{font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;color:#20334a;background:#edf2f7;margin:0;line-height:1.75}main{max-width:1120px;margin:32px auto;background:white;padding:42px 52px;box-shadow:0 4px 30px #24385012}h1{font-size:32px;line-height:1.4;border-bottom:3px solid #3578b5;padding-bottom:20px}h2{font-size:23px;color:#245b8c;margin-top:34px}p,li{font-size:16px}a{color:#246ea8}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.6;margin:20px 0;table-layout:fixed}th{background:#edf3fa}td,th{padding:9px 8px;border:1px solid #c7d5e4;overflow-wrap:anywhere;text-align:left}pre{font-family:monospace;white-space:pre-wrap;background:#f2f6fa;padding:20px;font-size:14px;line-height:1.6}figure{margin:28px 0}figure img{width:100%;height:auto}figcaption{font-size:14px;color:#516b83;line-height:1.65}code{overflow-wrap:anywhere}.download{background:#eef5fc;padding:12px 18px;border-radius:7px} @page{size:A4;margin:17mm 16mm} @page figure{size:A3 landscape;margin:12mm} @page distribution{size:420mm 420mm;margin:12mm} @media print{body{background:white}main{max-width:none;margin:0;padding:0;box-shadow:none}p,li{font-size:10pt;line-height:1.75}h1{font-size:23pt}h2{font-size:15pt;break-after:avoid}table{font-size:8pt;break-inside:avoid;margin:10px 0}td,th{padding:5px 6px}p{margin:8px 0}h2{margin-top:22px}tr{break-inside:avoid}pre{font-size:9pt;break-inside:avoid}.appendix-title{break-before:page}.report-figure{page:figure;break-before:page;break-after:page;margin:0}.distribution-page{page:distribution}figcaption{font-size:10pt}.download{display:none}a{color:#245b8c;text-decoration:none}}'''
 for folder,(title,md) in docs.items():
  target=out/folder;target.mkdir(exist_ok=True);(target/'REPORT.md').write_text(md)
  content=MarkdownIt('commonmark',{'html':True}).enable('table').render(md)
  content=content.replace('<h2>附表：','<h2 class="appendix-title">附表：')
  # Embed figure bytes so the HTML report itself is portable; retain source links.
  for path in (out/'figures').glob('*.svg'):
   content=content.replace(f'src="../figures/{path.name}"',f'src="data:image/svg+xml;base64,{base64.b64encode(path.read_bytes()).decode()}"')
  (target/'REPORT.html').write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style><main><div class="download"><a href="REPORT.pdf">下载PDF</a> · <a href="REPORT.md">Markdown</a> · <a href="../index.html">两份报告入口</a></div>{content}</main></html>')
 (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Trace诊断报告</title><h1>并发与资源分析</h1><p><strong>主要报告：</strong><a href="concurrency/REPORT.html">并发执行与资源占用分析</a> · <a href="concurrency/REPORT.pdf">PDF</a></p><p>定位参考：<a href="high_latency/REPORT.html">六个Process的五堆时间分布总览</a> · <a href="high_latency/REPORT.pdf">PDF</a> · <a href="PROCESS_INDEX.html">Process索引</a></p><p><a href="../index.html">返回交互时间线入口</a></p>')
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
  for folder in docs:
   page=browser.new_page(viewport={'width':1500,'height':1100});page.goto((out/folder/'REPORT.html').resolve().as_uri(),wait_until='networkidle');page.evaluate('document.fonts.ready');page.pdf(path=str(out/folder/'REPORT.pdf'),print_background=True,prefer_css_page_size=True);page.screenshot(path=str(out/folder/'preview.png'));page.close()
  browser.close()
 source_paths=[repo/'perf_trace/skills/build-optimization-trace-report/SKILL.md',repo/'perf_trace/skills/qwen-dcu-workflow05-trace-visualization-reporting/references/process-resource-contract.md',repo/'workload_profile/fx/traces/20260729T050800Z-fx-89687ae2-R032-qwen35-27b-eager-row0-hcu0/input1_layer0/fx_process_reconstruction.md',root/'batch8_report/site/source_snapshot/vllm/v1/engine/core_client.py']
 manifest={'status':'generated_pending_document_audit','reports':['concurrency','high_latency'],'regenerated_reports':list(docs),'paired_windows':windows,'both_view_types_in_concurrency_report':True,'latency_overview_only':False,'latency_profile':'rectangle overview plus longest-member rectangular zoom','primary_report':'concurrency','expanded_resource_windows':len(extra),'all_overlap_inventory':inventory,'all_selected_process_types_reported':items,'concurrency_cases':cases,'facts_sources':{k:{'path':f['source_page'],'sha256':f['source_sha256']} for k,f in facts.items()},'supporting_sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_paths],'scripts':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [Path(__file__),Path(__file__).with_name('analyze_trace_diagnostic_reports.py'),Path(__file__).with_name('capture_diagnostic_report_figures.py'),Path(__file__).with_name('expand_process_and_concurrency_examples.py'),Path(__file__).with_name('audit_trace_diagnostic_reports.py'),Path(__file__).with_name('analyze_concurrency_windows.py'),Path(__file__).with_name('render_report_time_distributions.py')]],'new_acquisition':False,'before_after_speedup_claimed':False,'outputs':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['concurrency','high_latency'] for p in (out/folder).iterdir()}}
 (out/'REPORT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print('Two reports generated: Markdown, self-contained HTML, PDF',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--repo',type=Path,required=True);p.add_argument('--only-high',action='store_true');a=p.parse_args();main(a.root.resolve(),a.repo.resolve(),a.only_high)
