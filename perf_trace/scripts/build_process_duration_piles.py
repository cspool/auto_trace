#!/usr/bin/env python3
"""Rebuild both retained trace presentations as >10% Process types / five duration piles.
Original release pages, tables and classification remain immutable. No acquisition.
"""
import argparse, base64, bisect, collections, csv, gzip, hashlib, html, json, math, re
from pathlib import Path
ASSETS=Path(__file__).with_name('process_pile_assets')
PAGES=['HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','CONCURRENCY_UTILIZATION.html']
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def read_page(p,single):
 s=p.read_text()
 encoded=re.search(r'<script[^>]*id="page-payload"[^>]*>(.*?)</script>',s,re.S)[1] if single else s.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0]
 return json.loads(encoded)
def rows(pack):
 for block in pack['blocks']:
  for a in json.loads(gzip.decompress(base64.b64decode(block))):yield dict(pack['constants'],**dict(zip(pack['fields'],a)))
def piles(ps):
 """Deterministic 1-D log-duration Lloyd clustering, followed by contiguous splits.
 Tied durations stay together unless all remaining splits require ties. No invented rows.
 """
 ordered=sorted(ps,key=lambda p:(p['d'],p['id']))
 if len(ordered)<5:raise ValueError('At least five actual instances required')
 xs=[math.log(p['d']) for p in ordered]
 centers=[xs[round(i*(len(xs)-1)/4)] for i in range(5)]
 last=None
 for _ in range(100):
  buckets=[[] for _ in range(5)]
  for i,x in enumerate(xs):buckets[min(range(5),key=lambda j:(abs(x-centers[j]),j))].append(i)
  buckets=[b for b in buckets if b]
  while len(buckets)<5:
   eligible=[b for b in buckets if len(b)>1]
   target=max(eligible,key=lambda b:(xs[b[-1]]-xs[b[0]],len(b),-b[0]))
   cuts=[i for i in range(1,len(target)) if xs[target[i-1]]<xs[target[i]]]
   cut=min(cuts,key=lambda i:abs(i-len(target)/2)) if cuts else len(target)//2
   buckets.remove(target);buckets.extend([target[:cut],target[cut:]])
  buckets.sort(key=lambda b:b[0])
  signature=tuple(tuple(b) for b in buckets)
  if signature==last:break
  last=signature
  centers=[sum(xs[i] for i in b)/len(b) for b in buckets]
 # Partition comes from actual assigned members, preserving every instance exactly once.
 out=[]
 for rank,b in enumerate(sorted(buckets,key=lambda b:b[0]),1):
  members=[ordered[i] for i in b];center=sum(math.log(p['d']) for p in members)/len(members)
  representative=min(members,key=lambda p:(abs(math.log(p['d'])-center),p['id']))
  out.append(dict(rank=rank,members=[p['id'] for p in members],representative=representative['id'],min_ns=members[0]['d'],max_ns=members[-1]['d'],center_ns=math.exp(center),high_count=sum(p['high'] for p in members)))
 assert len(out)==5 and sum(len(x['members']) for x in out)==len(ps)
 assert all(a['max_ns']<=b['min_ns'] for a,b in zip(out,out[1:]))
 return out

def normalize(root,key):
 single=key=='single_batch';source=root/key/'site';source=source if single else source/'acceptance'
 paths=[source/n for n in PAGES];H=read_page(paths[0],single);C=read_page(paths[1],single)
 origin=int(H['scope']['origin_ns'] if single else H['origin_ns'])
 def off(x):return int(x)-origin
 proc=[];kernels=[];samples=[];counts=[];metrics=collections.defaultdict(list);classifications={};availability={}
 if single:
  h=H['high'];c=C['concurrency'];dev=str(H['scope']['physical_device_id'])
  classifications={r['process']:r for r in h['processes']}
  for p in H['processes']:
   proc.append(dict(id=p['process'],name=p['stage'],b=off(p['b']),e=off(p['e']),d=int(p['e'])-int(p['b']),device=dev,request='single request',phase=p['phase'],layer=p['layer'],forward=p['forward'],fragment='',high=p['process'] in classifications,event=p['event']))
  for k in h['kernels']:kernels.append([k['process'],off(k['b']),off(k['e']),dev,k['queue'],k['n'],k['kernel_id']])
  for s in h['samples']:samples.append([off(s['t']),float(s['mean']),dev,s['eligible'],str(s.get('uncertainty',''))])
  for n,table in [('kernel',c['kernel_concurrency']),('queue',c['queue_concurrency'])]:
   for r in table:counts.append([off(r['b']),off(r['e']),dev,n,int(r['n'])])
  availability={p['process_range']:dict(p,mean_source='retained opportunity mean_se_active_cu_pct') for p in c['opportunities']}
  availability.update({p['process_range']:p for p in h['process_live']})
  hardware=collections.defaultdict(list)
  for r in h['hardware']:hardware[(r['event_id'],r['stage'],r['matched_kernel_family'])].append(r)
  for a in h['attachments']:
   for r in hardware[(a['event_id'],a['stage'],a['matched_kernel_family'])]:
    if r not in metrics[a['process_range']]:metrics[a['process_range']].append(r)
  scope=H['scope']
 else:
  ht=H['tables'];ct=C['tables'];classifications={r['process_range_id']:r for r in rows(ht['high_latency_processes'])}
  for p in rows(ht['process_timeline']):
   proc.append(dict(id=p['process_range_id'],name=p['process_id'],b=off(p['begin_ns']),e=off(p['end_ns']),d=int(p['end_ns'])-int(p['begin_ns']),device=p['physical_device_id'],request=p['request_id'],phase=p['phase'],layer=p['layer_idx'],forward=p['forward_id'],fragment=p.get('fragment_id',''),high=p['process_range_id'] in classifications))
  for k in rows(ht['kernel_timeline']):kernels.append([k['owner_process_range_id'],off(k['begin_ns']),off(k['end_ns']),k['physical_device_id'],k['queue_id'],k['native_kernel_name'],k['kernel_instance_id']])
  for s in rows(ct['live_utilization_aligned']):
   if s['record_kind']=='sample':samples.append([off(s['sample_midpoint_realtime_ns']),float(s['se_active_cu_pct']) if s['se_active_cu_pct'] else None,s['native_device'],s['timing_eligible']=='True',s['alignment_uncertainty_ns']])
  for n in ['kernel','queue']:
   for r in rows(ct[n+'_concurrency']):
    if r['scope_type']=='device':counts.append([off(r['begin_ns']),off(r['end_ns']),r['physical_device_id'],n,int(r['active_'+n+'_count'])])
  fields=['metric_name','value','unit','evidence_class','availability_state','availability_reason','runtime_shape_match','runtime_shape_comparison_permitted','join_state','source_row_id','physical_attribute_id','r07_kernel_instance_id','counter_mode','formula','assumptions','source_path','source_sha256']
  for m in rows(ht['traffic_resource_attachment']):metrics[m['r07_process_range_id']].append({f:m.get(f,'') for f in fields})
  for r in rows(ht['process_live_utilization']):availability[r['process_range_id']]={k:r.get(k,'') for k in ['availability_state','se_active_cu_pct_mean','timing_eligible_sample_count','intersecting_gap_count','process_sidecar_alignment_uncertainty_ns']}
  scope={'traced':'8 requests: first prefill and first decode process trace; rank0/DCU0 and rank1/DCU1. Not all decode steps.','cross_device_clock_bound':'unavailable','timeline_coverage_scope':H.get('timeline_coverage_scope')}
 assert all(p['d']>0 for p in proc) and len({p['id'] for p in proc})==len(proc)
 groups=collections.defaultdict(list)
 for p in proc:groups[p['name']].append(p)
 total_process_ns=sum(p['d'] for p in proc)
 selected=sorted((n for n in groups if sum(p['d'] for p in groups[n])*10>total_process_ns),key=lambda n:(-sum(p['d'] for p in groups[n]),n))
 if not selected:raise ValueError('No Process type exceeds the strict 10% threshold; current retained adapter cannot render an empty selection. Do not broaden the selection or fabricate piles.')
 result=[dict(rank=i+1,name=n,share=sum(p['d'] for p in groups[n])/total_process_ns,total_ns=sum(p['d'] for p in groups[n]),count=len(groups[n]),high_count=sum(p['high'] for p in groups[n]),piles=piles(groups[n])) for i,n in enumerate(selected)]
 flat=[]
 for g in result:
  for pile in g['piles']:
   pile['total_ns']=sum(p['d'] for p in groups[g['name']] if p['id'] in set(pile['members']))
   flat.append(dict(group=g['name'],pile_rank=pile['rank'],total_ns=pile['total_ns']))
 flat.sort(key=lambda x:(-x['total_ns'],x['group'],x['pile_rank']))
 resources={}
 for p in proc:
  a=availability.get(p['id'],{});value=a.get('mean_se_active_cu_pct') if single else a.get('se_active_cu_pct_mean')
  valid=(single or a.get('availability_state')=='available')
  try: compute=float(value)
  except (ValueError,TypeError):compute=None
  if not valid or compute is None or not math.isfinite(compute) or not 0<=compute<=100:compute=None
  resources[p['id']]=dict(compute_pct=compute,compute_metric='R07 same-device SE active CU percent, observed Process-window mean',compute_source='retained mean_se_active_cu_pct' if single else 'process_live_utilization.se_active_cu_pct_mean',compute_reason='' if compute is not None else a.get('availability_state',a.get('status','unavailable')),bandwidth_pct=None,bandwidth_reason='No verified R07 bandwidth utilization percent: replay bytes / L2 hit rate are not same-clock bandwidth utilization')
 begin=min(p['b'] for p in proc);end=max(p['e'] for p in proc)
 time_sections=[[begin+(end-begin)*i//10,begin+(end-begin)*(i+1)//10] for i in range(10)]
 provenance=[dict(path=str(p.resolve()),sha256=digest(p),size=p.stat().st_size) for p in paths]
 return dict(resources=resources,pile_order=flat,time_sections=time_sections,total_process_ns=total_process_ns,trace=key,origin_ns=str(origin),scope=scope,groups=result,processes=proc,kernels=kernels,samples=samples,counts=counts,metrics=metrics,classifications=classifications,availability=availability,source=provenance,all_group_count=len(groups),scale_max_ns=max(p['d'] for p in proc if p['name'] in selected),policy={'group_key':'Process type (single: stage; batch8: process_id)','group_ranking':'only types with sum(duration)*10 > sum(all Process durations), no concurrency deduplication; no fixed group count; global pile order by sum(duration) descending, then type name and pile index','clustering':'deterministic 1-D log-duration Lloyd clustering, 5 nonempty contiguous piles; tie splitting only if necessary','representative':'actual member nearest log-duration cluster mean; ID tie break','length':'one common piecewise-linear folded absolute-time axis for all selected pile lanes; consecutive selected event endpoint intervals capped at 2 * median process duration by default; reversible and configurable; preserves simultaneous positions; linear mode width = duration * common pixels_per_ns; subpixel presence markers','formal_r10_regeneration':False,'original_acceptance_untouched':True})

def build(root,key,refresh_assets=False):
 out=root/'revised'/key
 if refresh_assets:
  raw=(out/PAGES[0]).read_text();encoded=re.search(r'<script id="packed"[^>]*>(.*?)</script>',raw,re.S)[1]
  data=json.loads(gzip.decompress(base64.b64decode(encoded)))
  for source in data['source']:assert digest(source['path'])==source['sha256']
  assert 'pile_order' in data and 'resources' in data and len(data['time_sections'])==10
 else:data=normalize(root,key)
 replay_path=root/'batch8_bandwidth/PROCESS_BANDWIDTH.json'
 if key=='batch8' and replay_path.exists():
  replay=json.loads(replay_path.read_text());audit=json.loads((replay_path.parent/'CALCULATION_AUDIT.json').read_text())
  assert audit['status']=='complete' and digest(replay_path)==audit['outputs']['PROCESS_BANDWIDTH.json']
  data['bandwidth_replay']={'source':str(replay_path.resolve()),'sha256':digest(replay_path),'reference':replay['reference'],'summary':audit['summary'],'projection':'same-shape selected-kernel replay attributes; never observed R07 live bandwidth; read/write are separate passes'}
  for ident,resource in data['resources'].items():
   resource['bandwidth_profiles']=replay['processes'].get(ident,{})
   resource['bandwidth_pct']=None
   resource['bandwidth_reason']='R07 live value unavailable; use separately labeled same-shape directional replay reference'
 l2_activity_path=root/'batch8_bandwidth/L2_ACTIVITY.json'
 if key=='batch8' and l2_activity_path.exists():
  l2=json.loads(l2_activity_path.read_text());assert l2['status']=='verified'
  assert digest(l2_activity_path.parent/'L2_ACTIVITY_DISPATCH.csv')==l2['csv_sha256']
  data['batch8_l2']={'source':str(l2_activity_path.resolve()),'sha256':digest(l2_activity_path),'summary':l2['summary'],'metric':'L2 hit rate and request rate from same PMC replay; NOT bandwidth utilization','bandwidth_GBps':None,'bandwidth_utilization_pct':None,'peak_GBps':None}
  for ident,resource in data['resources'].items():resource['l2_activity']=l2['profiles'].get(ident)
 if key=='single_batch':
  l2_rows=[]
  selected_ids={ident for g in data['groups'] for pile in g['piles'] for ident in pile['members']}
  for ident,resource in data['resources'].items():
   samples=[]
   for raw in data['metrics'].get(ident,[]):
    try: rate=float(raw['projected_L2_throughput_GBps_on_R07_latency_axis'])
    except (KeyError,ValueError,TypeError):continue
    if not math.isfinite(rate) or rate<0:continue
    sample=dict(sample_id=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),process_range=ident,kernel_family=raw['matched_kernel_family'],projected_L2_GBps=rate,mean_read_KB_per_replay_instance=raw['mean_L2_read_KB_per_replay_instance'],mean_write_KB_per_replay_instance=raw['mean_L2_write_KB_per_replay_instance'],L2_hit_rate_pct=raw['L2_hit_rate_pct'],evidence_class='retained_replay_projected_L2_throughput_on_R07_latency_axis',in_selected_piles=ident in selected_ids,original_row=raw)
    samples.append(sample);l2_rows.append(sample)
   resource['l2_samples']=samples
  data['l2_reference']={'peak_GBps':None,'reference_state':'unavailable_no_verified_L2_reference','hardware_rows':len(l2_rows),'processes_with_samples':sum(bool(r['l2_samples']) for r in data['resources'].values()),'selected_processes_with_samples':sum(bool(data['resources'][i]['l2_samples']) for i in selected_ids),'selection':'first retained family sample by default; choose another sample explicitly; no sum or average across families','units':'GB/s retained from original projected field; not actual R07 or same-pass R08 bandwidth','visual_scale_GBps':[500,1000,1500],'HBM_reference_used':False}
  l2_out=root/'single_batch_bandwidth';l2_out.mkdir(exist_ok=True)
  dump(l2_out/'L2_PROJECTED_SAMPLES.json',{'reference':data['l2_reference'],'samples':l2_rows,'source':data['source']})
  with (l2_out/'L2_PROJECTED_SAMPLES.csv').open('w',newline='') as handle:
   fields=[k for k in l2_rows[0] if k!='original_row'];writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows({k:r[k] for k in fields} for r in l2_rows)
 # Diagnose missing values without replacing them or rewriting source states.
 if key=='single_batch':
  eligible_times=sorted(s[0] for s in data['samples'] if s[3])
  for p in data['processes']:
   r=data['resources'][p['id']]
   if r['compute_pct'] is None:
    n=bisect.bisect_left(eligible_times,p['e'])-bisect.bisect_left(eligible_times,p['b'])
    r['diagnostic_eligible_points_count']=n
    r.setdefault('original_compute_reason',r.get('compute_reason'))
    r['compute_reason']='unavailable_too_few_samples' if n<3 else 'unavailable_original_mean'
 def compute_state(r):
  if r['compute_pct'] is not None:return 'available'
  reason=r.get('compute_reason','')
  return {'unavailable_intrinsic_short_window':'short_window','unavailable_too_few_samples':'too_few_samples','unavailable_sampling_gap':'sampling_gap','unavailable_alignment_error':'alignment_error'}.get(reason,'missing_mean')
 def replay_state(profile,value):
  if not profile:return 'not_sampled'
  if profile.get(value) is not None:return 'available'
  return {'unavailable_shape_mismatch':'shape_mismatch','unavailable_counters_or_duration':'invalid_counter_or_duration','unavailable_shape_or_counter':'shape_or_counter'}.get(profile.get('state'),'missing_metric')
 selected_ids={i for g in data['groups'] for c in g['piles'] for i in c['members']}
 diagnostic={}
 for p in data['processes']:
  r=data['resources'][p['id']];r['compute_state']=compute_state(r)
  if p['id'] not in selected_ids:continue
  states={'compute':r['compute_state']}
  if key=='batch8':
   for direction in ['read','write']:states[direction]=replay_state(r.get('bandwidth_profiles',{}).get(direction),'reference_pct')
   states['l2']=replay_state(r.get('l2_activity'),'hit_rate_pct')
  else:states['l2_projected']='available' if r.get('l2_samples') else 'no_l2_sample'
  diagnostic[p['id']]={'process_type':p['name'],'fragment':p['fragment'],'states':states}
 metric_names=list(next(iter(diagnostic.values()))['states'])
 coverage={'selected_instances':len(selected_ids),'metrics':{m:dict(collections.Counter(row['states'][m] for row in diagnostic.values())) for m in metric_names},'by_type_fragment':[],'values_filled':False}
 for group in sorted({(r['process_type'],r['fragment']) for r in diagnostic.values()}):
  entries=[r for r in diagnostic.values() if (r['process_type'],r['fragment'])==group]
  coverage['by_type_fragment'].append({'process_type':group[0],'fragment':group[1],'instances':len(entries),'metrics':{m:dict(collections.Counter(r['states'][m] for r in entries)) for m in metric_names}})
 data['resource_coverage']=coverage
 out.mkdir(parents=True,exist_ok=True)
 dump(out/'RESOURCE_COVERAGE.json',coverage)
 dump(out/'GROUPS.json',{k:data[k] for k in ['trace','groups','pile_order','time_sections','total_process_ns','policy','source','scope']})
 packed=base64.b64encode(gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode(),mtime=0)).decode()
 css=(ASSETS/'piles.css').read_text();js=(ASSETS/'piles.js').read_text()
 for mode,name,title in [('high',PAGES[0],'高延迟分析'),('concurrency',PAGES[1],'并发分析')]:
  original=('../../'+key+'/site/'+('acceptance/' if key=='batch8' else '')+name)
  full='../../'+key+'/site/'+('acceptance/' if key=='batch8' else '')+'E2E_PROCESS_TIMELINE_LOSSLESS.html'
  nav=f'<a href="../../index.html">全部报告</a><a href="{PAGES[0]}">高延迟分析</a><a href="{PAGES[1]}">并发分析</a><a href="{original}">原版完整证据与其他分析</a><a href="{full}">完整绝对时间线</a>'
  if data.get('bandwidth_replay'):nav+='<a href="../../batch8_bandwidth/README.md">重放带宽计算与覆盖率</a>'
  reference_gbps=data.get('bandwidth_replay',{}).get('reference',{}).get('bandwidth_reference',{}).get('value')
  resource_note=(f'已恢复 R08 同条 PMC 计数与耗时。下方蓝色虚线子矩形展示读或写重放带宽相对 {reference_gbps} GB/s 文档实测参考的百分比，可切换方向；这是所选 kernel 的重放属性投影，不是 R07 同时刻实测带宽。形状不匹配、计数缺失或耗时无效仍为未知。超过100%的数值原样保留，高度落在最高档。' if data.get('bandwidth_replay') else '当前来源缺少可用的 R07 带宽利用率百分比，带宽子矩形保留为未知；R08重放计数不冒充观测时间分布。')
  if data.get('l2_reference'):
   nav+='<a href="../../single_batch_bandwidth/L2_README.md">L2 吞吐量与资源参考说明</a>'
   resource_note='下方蓝色子矩形现在显示 L2 投影吞吐量（GB/s），四档为 ≤500、500–1000、1000–1500、>1500 GB/s，不是利用率百分比。尚无已验证的 L2 带宽基准，百分比默认未知；可输入用户指定的 L2 基准，查看相对该基准的投影占比。不能使用 HBM 1206 GB/s。默认显示每个 Process 第一条保留样本；可切换其他 kernel family，不相加或平均。L2 命中率单列，不能作为带宽利用率。'
  if data.get('batch8_l2'):
   nav+='<a href="../../batch8_bandwidth/L2_README.md">L2 命中率与请求速率</a>'
   resource_note+=' 另可切换紫色 L2 子矩形：命中率按百分比四档，请求速率按 ≤5、5–10、10–15、>15 Grequest/s 四档（每秒十亿次请求）。命中率和请求速率都不是 L2 带宽利用率；没有假设每次请求的字节数或套用 HBM 基准。'
  content=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{key} · {title} · >10% Process</title><style>{css}</style><header><div class="eyebrow">{'单 batch · DCU1' if key=='single_batch' else 'Batch8 · 双卡 DP2'} / PROCESS TIMELINES</div><h1>{title} <span>累计时长占比 &gt;10%</span></h1><nav>{nav}</nav></header><main><section class="intro"><h2>{'Process 执行时间分布' if mode=='high' else '计算 / 带宽资源占用率分布'}</h2><p>仅选择该类型 Process 累计执行时长占全部 Process 时长求和严格超过 10% 的类型；不扣除并发重叠，不要求 10 组。每种类型按相近执行时长聚成 5 堆，再将全部堆按各自累计执行时长降序排列在同一图中。两种分析的堆顺序完全相同。</p><p>完整真实时间范围等分成 10 段，每次只显示其中一段；可切换段号、同步缩放和平移。跨段实例按窗口裁切显示，源起止和时长不变。所有轨道共用一个可折叠时间轴，// 表示压缩，可调整折叠强度或恢复线性。</p><p>{'矩形宽度表示 Process 执行时间范围，颜色区分设备；红色边缘保留原始高延迟标记。排名使用全部实例累计时长，不重新分类。' if mode=='high' else '每个实例包含上下两个同起止的子矩形：上方绿色为计算活跃率代理（SE active CU%），下方蓝色为带宽利用率。高度四档对应 [0,25]、(25,50]、(50,75]、(75,100]%。计算值是该设备在 Process 窗口内的原始观测均值，不表示连续恒定利用率或该 Process 独占资源。灰色斜纹为未知，不属于四档，也不是 0%。' + resource_note}</p><p>Process 父过程与 fragment 可重叠，累计值不是 E2E wall time。{'仅有单设备证据。' if key=='single_batch' else '双卡同轴不证明精确跨卡并发；本样例只追踪每个请求首个 prefill/decode。'}</p><p id="status" role="status">正在读取本地内嵌数据…</p><div id="coverageSummary"></div></section><section class="timeline"><div class="sticky-axis"><div id="controls"></div><div id="navigation"></div><p id="viewState"></p><canvas id="axis"></canvas></div><canvas id="timeline" aria-label="同一时间轴上的全部入选Process堆"></canvas></section><aside id="details" hidden><button id="closeDetail">关闭详情</button><h2>所选实例与证据</h2><div id="detailBody"></div></aside></main><script id="packed" type="application/octet-stream">{packed}</script><script>const MODE={json.dumps(mode)};\n{js}</script></html>'''
  if data.get('l2_reference') and mode=='concurrency':content=content.replace('下方蓝色为带宽利用率。高度四档对应 [0,25]、(25,50]、(50,75]、(75,100]%。','下方蓝色为 L2 投影吞吐量。上方计算活跃率高度四档对应 [0,25]、(25,50]、(50,75]、(75,100]%。')
  if mode=='high':
   content=content.replace('矩形宽度表示 Process 执行时间范围，颜色区分设备；红色边缘保留原始高延迟标记。排名使用全部实例累计时长，不重新分类。','每堆以梯形外框组织组内全部可见实例，每条横线保留真实起止位置；所有堆共用同一时间轴。梯形外框仅表示分组，不表示连续执行。原始高延迟标记保留为红色，其他颜色区分设备。')
  else:
   start=content.index('<p>每个实例包含');stop=content.index('</p>',start)+4
   if data.get('batch8_l2'):
    text='每个实例同时包含计算（绿）、DRAM读（蓝）、DRAM写（橙）、L2命中率（紫）、L2请求速率（粉）五个子矩形，不再轮流切换。高度与数值连续成比例：百分比24px/100%，L2请求速率24px/15 Grequest/s；百分比超过参考上限时扩展该指标的显示比例尺并保留原值。计算为R07 SE活跃率均值，其余为形状匹配的R08重放属性；它们不是同一次测量。L2命中率和请求速率不是L2带宽利用率。'
   else:
    text='每个实例同时显示计算活跃率和L2投影吞吐量，子矩形高度与各自数值连续成比例。计算百分比使用24px/100%的比例尺；L2以GB/s使用独立比例尺，可输入用户L2带宽基准查看相对占比。L2投影和命中率不能冒充真实L2带宽利用率。'
   text+=' 过短采样窗口用ε极小占位标记表示，数据仍为未知，ε不是实测低利用率；其他缺失项标注具体原因。0值只画基线，不补成正数。不同单位与资源比例尺在图前注明。'
   content=content[:start]+'<p>'+text+'</p>'+content[stop:]
  if mode=='concurrency':content=content.replace('<p id="status"', '<p>默认隐藏未采集、未关联和无有效值的资源项；默认仅保留有已关联硬件指标的实例；只有计算活跃率而无硬件关联的实例不显示，空堆隐藏且保留原排名。只有所有可见轨道都无可显示数据的时间区间才跳过，以 » 标断点，不代表设备空闲；若其他轨道有有效数据，该时段保留。可恢复全部实例和原始时间区间，数据与排名不变。高延迟图仍保留实际采集到的 Process，资源缺失不等于 Process 未执行。</p><p id="status"')
  (out/name).write_text(content)
 (out/'index.html').write_text(f'<!doctype html><meta charset="utf-8"><title>{key} · >10% Process 时间线</title><h1>{key} · >10% Process · 按堆总延迟排序</h1><p><a href="{PAGES[0]}">高延迟分析</a></p><p><a href="{PAGES[1]}">并发分析</a></p><p><a href="../../index.html">返回全部报告</a></p>')
 dump(out/'BUILD_MANIFEST.json',dict(status='built',source=data['source'],resource_coverage=data.get('resource_coverage'),bandwidth_replay=data.get('bandwidth_replay'),l2_reference=data.get('l2_reference'),batch8_l2=data.get('batch8_l2'),policy=data['policy'],group_count=len(data['groups']),pile_count=len(data['pile_order']),process_count=len(data['processes']),kernel_count=len(data['kernels']),sample_count=len(data['samples']),source_code={str(p):digest(p) for p in [Path(__file__),*sorted(ASSETS.glob('*'))]},outputs={n:digest(out/n) for n in [*PAGES,'GROUPS.json']}))
 print(key,'built:',len(data['processes']),'processes;',len(data['samples']),'samples;',len(data['groups']),'groups;',len(data['pile_order']),'globally ranked piles; 10 time sections',flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--refresh-assets',action='store_true',help='Re-render a verified current normalized payload without repeating source normalization');parser.add_argument('--trace',choices=['single_batch','batch8','both'],default='both');a=parser.parse_args()
 for key in (['single_batch','batch8'] if a.trace=='both' else [a.trace]):build(a.root.resolve(),key,a.refresh_assets)
