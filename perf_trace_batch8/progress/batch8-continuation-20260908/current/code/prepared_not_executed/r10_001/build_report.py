"""Render complete accepted R09 data into local, self-contained R10 pages."""
from pathlib import Path
import csv,json,hashlib,gzip,base64,html,time,sys,collections,os
ROOT=Path(__file__).parents[2];ACCEPT=ROOT/'acceptance';TOOLS=Path(__file__).parent
NAMES=['request_timeline','process_timeline','kernel_timeline','live_utilization_aligned','process_live_utilization','kernel_concurrency','queue_concurrency','launch_gaps','high_latency_processes','dependency_state','traffic_resource_attachment','opportunity_candidates']
def check(x,m):
 if not x:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rec(p):return {'path':str(p),'size':Path(p).stat().st_size,'sha256':sha(p)}
def js(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(js(x).encode()).hexdigest()
def rows(p):
 with Path(p).open(newline='') as f:yield from csv.DictReader(f)
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False,sort_keys=True);f.write('\n')
LEGEND='<div class="legend"><span class="badge observed">observed R07 timing｜观测时间</span><span class="badge live">observed live utilization｜原始利用率</span><span class="badge replay">replay_projected R08 hardware attributes｜重放属性</span><span class="badge derived">derived analysis｜派生分析</span><span class="badge unknown">unavailable/unknown evidence｜未知</span></div>'
NOTICE='完整覆盖 R06 声明的首个 prefill/decode 过程目标及八请求的实际客户端区间；不声称全部 1024 个解码步骤均有过程 trace。重放计数器不替换观测延迟；kernel 的两种显示副本不重复计时；不同运行形状不能直接比较资源。'
TIMELINE_BODY='''<section><div class="controls"><button id="zoomIn">放大</button><button id="zoomOut">缩小</button><button id="resetView">全范围</button><button id="backView">后退</button><button id="forwardView">前进</button><button id="toggleDensity">切换密度显示</button><button id="fitFilter">适配全部过滤结果</button><button id="listViewport">列出视窗内全部事件</button></div><p>滚轮以指针为中心缩放；拖动平移；Shift 拖动框选缩放；最小视窗 1 ns。历史不设 100 步以内的截断。</p><div class="controls filters">''' + ''.join('<label>'+label+' <input data-filter="'+field+'" type="text"></label>' for field,label in [('process','过程'),('event','事件'),('layer','层'),('phase','阶段'),('family','家族'),('track','轨道'),('request_id','请求')])+'''</div><div class="controls"><label>绝对开始 ns <input id="jumpBegin" type="text"></label><label>绝对结束 ns <input id="jumpEnd" type="text"></label><button id="jumpView">精确跳转</button><label>原始事件 ID <input id="eventId" type="text"></label><button id="locateEvent">独立定位原始事件</button></div><p id="viewState" class="mono"></p><div id="plotScroll" class="plot-scroll"><canvas id="timelineCanvas"></canvas><div id="trackSpacer"></div></div><p>轨道纵向滚动仅控制屏幕绘制；全量数据、时间窗口检索与源事件定位均保留。</p></section><section><p id="listCount">点击时间像素或列出当前视窗，显示全部相交事件。</p><div id="eventList" class="event-list"></div></section>'''
HARDWARE_BODY='<section><p id="classificationState"></p><div id="highRows" class="scroll-table"></div></section>'
CONCURRENCY_BODY='''<section><p id="liveState"></p><div id="unionRows" class="scroll-table"></div><div class="controls"><label>绝对开始 ns <input id="liveBegin" type="text"></label><label>绝对结束 ns <input id="liveEnd" type="text"></label><button id="liveApply">显示原始点</button><label>完整 live 表行索引 <input id="sampleIndex" value="0" type="text"></label><button id="inspectSample">查看精确原始行</button></div><canvas id="liveCanvas"></canvas><p class="notice">紫色区间是采样未知间隙，不是零利用率。已选 kernel 之间的间隔可能包含未选择的执行，不能称为 GPU 空闲。</p></section>''' + ''.join('<section><h2>'+title+'</h2><div id="'+identifier+'" class="scroll-table"></div></section>' for identifier,title in [('kernelConcurrencyRows','Kernel 并发：全部精确分段'),('queueConcurrencyRows','队列并发：全部精确分段'),('launchGapRows','严格归属 kernel 的相邻间隔与重叠'),('processAvailabilityRows','全部过程的利用率可用性'),('samplingGapRows','全部原始采样间隙')])
def pack_table(meta):
 # Values that are constant across the entire table are stored once, without
 # losing a field. All remaining string cells are packed in lossless blocks.
 constants=None;fields=meta['schema'];count=0
 for r in rows(meta['path']):
  count+=1
  if constants is None:constants=dict(r)
  else:
   for k in list(constants):
    if r[k]!=constants[k]:del constants[k]
 check(count==meta['row_count'],'full source row count');constants=constants or {};vary=[f for f in fields if f not in constants];blocks=[];chunk=[];raw_hash=hashlib.sha256();row_hashes=[];keep_hashes=meta['logical_name'] in ['request_timeline','process_timeline','kernel_timeline']
 for r in rows(meta['path']):
  values=[r[f] for f in vary]
  if keep_hashes:row_hashes.append(digest(r))
  raw_hash.update((js([r[f] for f in fields])+'\n').encode());chunk.append(values)
  if len(chunk)==1000:blocks.append(base64.b64encode(gzip.compress(js(chunk).encode(),compresslevel=3,mtime=0)).decode());chunk=[]
 if chunk:blocks.append(base64.b64encode(gzip.compress(js(chunk).encode(),compresslevel=3,mtime=0)).decode())
 return {'source_row_hashes':row_hashes,'fields':vary,'original_schema':fields,'constants':constants,'row_count':count,'source_table_sha256':meta['sha256'],'canonical_rows_sha256':raw_hash.hexdigest(),'blocks':blocks,'encoding':'lossless string cells; constant columns plus base64 gzip JSON row blocks'}
def main():
 started=time.monotonic();assignment=read(ROOT/'authorization/assignment.json');check(assignment['runtime_goal']=='R10','R10 stage assignment');check(assignment['predecessor_stages']==['R%02d'%i for i in range(1,10)],'exact R01-R09 prefix')
 for x in assignment['predecessor_handoffs']+assignment['consumed_sources']:check(sha(x['path'])==x['sha256'],'sealed predecessor bytes')
 handoff=read(assignment['r09_handoff']['path']);check(handoff['status']=='complete' and handoff['evidence_status']=='complete' and handoff['coverage_target_met'] and not handoff['next_authorization_required'] and handoff['all_started_processes_terminated'],'R09 advance gate')
 source=Path(assignment['r09_analysis']['path']);check(sha(source)==assignment['r09_analysis']['sha256'],'exact accepted R09 analysis');analysis=read(source);check([t['logical_name'] for t in analysis['tables']]==NAMES,'exact twelve tables');metas={m['logical_name']:m for m in analysis['tables']}
 for m in metas.values():check(sha(m['path'])==m['sha256'] and Path(m['path']).stat().st_size==m['size'],'R09 table identity')
 request=list(rows(metas['request_timeline']['path']));process=list(rows(metas['process_timeline']['path']));kernel=list(rows(metas['kernel_timeline']['path']));check(len(request)==8 and {r['rank'] for r in request}=={'0','1'},'eight-request DP2 gate')
 for q in request:
  check(any(p['request_id']==q['request_id'] for p in process) and any(k['request_id']==q['request_id'] for k in kernel),'no untraced measured request')
 origin=min(int(r['begin_ns']) for r in request);req={r['request_id']:r for r in request};
 def track_for(kind,r):
  return 'request:'+r['request_id'] if kind=='request' else ('process:'+r['process_range_id'] if kind=='process' else ('kernel-owner:'+r['owner_process_range_id'] if kind=='strict_owned_kernel' else 'queue:'+r['rank']+':'+r['physical_device_id']+':'+r['queue_id']+':'+r['stream_id']))
 lanes={}
 for kind,items in [('request',request),('process',process),('strict_owned_kernel',kernel),('gpu_queue',kernel)]:
  ends_bytrack={}
  for r in sorted(items,key=lambda r:(int(r['begin_ns']),int(r['end_ns']),r.get('kernel_instance_id',r.get('process_range_id',r['request_id'])))):
   sid=r.get('kernel_instance_id',r.get('process_range_id',r['request_id']));track=track_for(kind,r);ends=ends_bytrack.setdefault(track,[]);free=next((i for i,end in enumerate(ends) if end<=int(r['begin_ns'])),len(ends))
   if free==len(ends):ends.append(int(r['end_ns']))
   else:ends[free]=int(r['end_ns'])
   lanes[kind,sid]=free
 count_expected=len(request)+len(process)+2*len(kernel);ACCEPT.mkdir(exist_ok=False);counts=collections.Counter();row_identity={};trace=ACCEPT/'E2E_PROCESS_TIMELINE.full.perfetto.json';first=True
 with trace.open('x') as out:
  out.write('{"displayTimeUnit":"ns","traceEvents":[')
  for kind,table,items,copy in [('request','request_timeline',request,0),('process','process_timeline',process,0),('strict_owned_kernel','kernel_timeline',kernel,0),('gpu_queue','kernel_timeline',kernel,1)]:
   for r in items:
    sid=r.get('kernel_instance_id',r.get('process_range_id',r['request_id']));b=int(r['begin_ns']);e=int(r['end_ns']);request_begin=int(req[r['request_id']]['begin_ns']);check(origin<=b<=e,'observed interval');counts[kind]+=1
    base_track=track_for(kind,r);track=base_track+'/lane:'+str(lanes[kind,sid])
    args={'base_track':base_track,'overlap_sub_lane':lanes[kind,sid],'source_table':table,'source_table_sha256':metas[table]['sha256'],'source_row_id':sid,'source_row_sha256':digest(r),'request_id':r['request_id'],'rank':r['rank'],'native_device':r['physical_device_id'],'absolute_begin_ns':str(b),'absolute_end_ns':str(e),'duration_ns':str(e-b),'origin_ns':str(origin),'relative_begin_ns':str(b-origin),'relative_end_ns':str(e-origin),'request_begin_ns':str(request_begin),'request_relative_begin_ns':str(b-request_begin),'request_relative_end_ns':str(e-request_begin),'display_copy_index':copy,'paired_kernel_display_copies_non_additive':kind in ['strict_owned_kernel','gpu_queue'],'observed_interval_sha256':digest([sid,str(b),str(e)]),'evidence_class':'observed_r07_timing','original_row':r}
    event={'name':r.get('native_kernel_name',r.get('process_id',r['request_id'])),'cat':kind,'ph':'X','pid':'rank:'+r['rank'],'tid':track,'ts':'EXACT_TS','dur':'EXACT_DUR','args':args};encoded=js(event).replace('"EXACT_TS"',str((b-origin)//1000)+'.'+str((b-origin)%1000).zfill(3)).replace('"EXACT_DUR"',str((e-b)//1000)+'.'+str((e-b)%1000).zfill(3));out.write(('' if first else ',')+encoded);first=False
  out.write('],"metadata":'+js({'complete_timeline':True,'sampling_performed':False,'formal_r09_r10_regeneration':True,'origin_ns':str(origin),'coverage_scope':analysis['timeline_coverage_scope'],'kernel_display_copies_non_additive':True})+'}')
 check(sum(counts.values())==count_expected,'full Perfetto formula');print('R10_PERFETTO_COMPLETE',count_expected,flush=True)
 packs={}
 for name in NAMES:
  packs[name]=pack_table(metas[name]);print('R10_PACKED_TABLE',name,packs[name]['row_count'],flush=True)
 css=(TOOLS/'viewer.css').read_text();javascript=(TOOLS/'viewer.js').read_text();pages=[]
 def page(filename,title,mode,names,body):
  payload={'mode':mode,'origin_ns':str(origin),'expected_event_count':count_expected,'coverage':analysis['batch8_coverage']['coverage'],'source_tables':analysis['tables'],'tables':{n:packs[n] for n in names},'lineage_id':analysis['lineage_id'],'derived_scope_summaries':analysis.get('derived_scope_summaries',[]),'timeline_coverage_scope':analysis['timeline_coverage_scope']};encoded=js(payload).replace('</','<\\/');path=ACCEPT/filename
  text='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+css+'</style><header><a href="index.html">验收入口</a><h1>'+html.escape(title)+'</h1>'+LEGEND+'<p class="notice">'+NOTICE+'</p><p>运行 '+analysis['runtime_run_id']+'；谱系 '+analysis['lineage_id']+'；8 请求 × 1024 token；DP2：rank0→设备0，rank1→设备1。</p></header><main><p id="loading">正在从内嵌字节恢复完整数据…</p><section><h2>八请求覆盖率</h2><div id="coverage" class="scroll-table coverage-matrix"></div></section>'+body+'<section><h2>精确源记录与证据</h2><pre id="details">选择记录后显示精确时间、源表、行身份、单位和可用性。</pre></section></main><script>const PAYLOAD='+encoded+';</script><script>'+javascript+'</script></html>'
  with path.open('x') as f:f.write(text)
  item={**rec(path),'format':'text/html','role':mode,'embedded_payload_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'embedded_javascript_sha256':hashlib.sha256(javascript.encode()).hexdigest(),'embedded_css_sha256':hashlib.sha256(css.encode()).hexdigest(),'embedded_tables':{n:{k:v for k,v in packs[n].items() if k!='blocks'} for n in names},'request_count':8,'ranks':[0,1],'native_devices':[0,1]};pages.append(item);print('R10_PAGE_CANDIDATE',filename,path.stat().st_size,flush=True)
 page('E2E_PROCESS_TIMELINE_LOSSLESS.html','完整过程时间线 · 精确纳秒离线浏览','timeline',['request_timeline','process_timeline','kernel_timeline'],TIMELINE_BODY)
 lossless=pages[-1];overview='<section><h2>完整事件总量：'+str(count_expected)+'</h2><p>'+str(len(request))+' 个请求 + '+str(len(process))+' 个过程 + 2 × '+str(len(kernel))+' 个 kernel 显示副本。逻辑 kernel 只计 '+str(len(kernel))+' 次。</p><p><a href="E2E_PROCESS_TIMELINE_LOSSLESS.html">打开全量可缩放时间线</a> · <a href="E2E_PROCESS_TIMELINE.full.perfetto.json">完整离线 Perfetto JSON</a></p><p class="mono">lossless SHA-256 '+lossless['sha256']+'<br>Perfetto SHA-256 '+sha(trace)+'</p></section>'
 page('E2E_PROCESS_TIMELINE.html','八请求端到端观测总览','overview',['request_timeline'],overview)
 page('HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','全部高延迟过程与硬件证据','hardware',['request_timeline','process_timeline','kernel_timeline','high_latency_processes','traffic_resource_attachment','process_live_utilization'],HARDWARE_BODY)
 page('CONCURRENCY_UTILIZATION.html','双卡并发、原始利用率与未知间隙','concurrency',['request_timeline','live_utilization_aligned','kernel_concurrency','queue_concurrency','launch_gaps','process_live_utilization'],CONCURRENCY_BODY)
 manifest={'schema_version':1,'status':'candidate_complete_pending_offline_and_independent_audit','runtime_run_id':analysis['runtime_run_id'],'runtime_goal':'R10','lineage_id':analysis['lineage_id'],'trace_profile_sha256':analysis['trace_profile_sha256'],'target':analysis['target'],'selected_request':assignment['selected_request'],'workload':assignment['workload'],'topology':assignment['topology'],'predecessor_handoffs':assignment['predecessor_handoffs'],'cumulative_runtime_ledger':assignment['cumulative_runtime_ledger'],'renderer_version':'lossless-batch8-viewer-1','assignment':rec(ROOT/'authorization/assignment.json'),'r09_analysis':rec(source),'r09_tables':analysis['tables'],'source_counts':{'requests':len(request),'processes':len(process),'kernels':len(kernel)},'event_count_formula':'requests + processes + 2*kernels','expected_event_count':count_expected,'actual_perfetto_event_count':sum(counts.values()),'event_class_counts':dict(counts),'complete_timeline':True,'sampling_performed':False,'formal_r09_r10_regeneration':True,'top_n_or_event_cap':False,'origin_ns':str(origin),'request_begin_ns':str(origin),'absolute_time_encoding':'decimal strings; subtraction with BigInt; Perfetto exact relative decimal microseconds','minimum_viewport_ns':1,'interval_semantics':'half-open; ends before starts; deterministic overlap lanes','coverage_scope':analysis['timeline_coverage_scope'],'batch8_coverage':analysis['batch8_coverage'],'utilization_counts':{k:v for k,v in analysis['row_universes'].items() if k.startswith('live_')},'replay_timing_used_as_latency':False,'kernel_display_copy_pairing_non_additive':True,'pages':pages,'perfetto':rec(trace),'tools':[rec(p) for p in sorted(TOOLS.iterdir()) if p.is_file()],'interpreter':rec(Path(sys.executable).resolve()),'argv':sys.argv,'elapsed_seconds':time.monotonic()-started}
 save(ACCEPT/'full_timeline_manifest.json',manifest)
 # The entry links to later audit files by their declared immutable paths.
 links=[('E2E_PROCESS_TIMELINE.html','观测总览'),('E2E_PROCESS_TIMELINE_LOSSLESS.html','完整可交互时间线'),('HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','全部高延迟过程与硬件'),('CONCURRENCY_UTILIZATION.html','双卡并发与原始利用率'),('E2E_PROCESS_TIMELINE.full.perfetto.json','完整 Perfetto JSON'),('full_timeline_manifest.json','时间线清单'),('offline_acceptance_manifest.json','离线验收清单'),('../R10_SOURCE_LINEAGE.json','来源谱系'),('../R10_COMPLETION_AUDIT.json','独立完成审计')]
 entry='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Batch8 DP2 R10 离线验收</title><style>'+css+'</style><header><h1>Batch8 DP2 · R10 离线验收</h1>'+LEGEND+'</header><main><section><p class="notice">'+NOTICE+'</p><p>8 个成功请求，双卡各 4 个请求；'+str(len(process))+' 个过程；'+str(len(kernel))+' 个唯一 kernel；'+str(count_expected)+' 个主显示事件。源代码 '+html.escape(analysis['target']['commit'])+'，谱系 '+analysis['lineage_id']+'。</p><p>此入口与审计文件一起封存。完成状态以独立完成审计为准；页面生成本身不代表通过验收。</p><ul>'+''.join('<li><a href="'+url+'">'+title+'</a></li>' for url,title in links)+'</ul><p>下载完整目录后直接打开本页，无须网络或服务。时间线支持滚轮缩放、拖动、Shift 框选、精确纳秒跳转和所有相交事件检索。机会项仅为调查假设，没有实测或预测加速结论。</p></section></main></html>'
 with (ACCEPT/'index.html').open('x') as f:f.write(entry)
 save(ROOT/'validation/RENDER_CANDIDATE_COMPLETE.json',{'status':'complete_pending_browser_and_independent_audit','full_timeline_manifest':rec(ACCEPT/'full_timeline_manifest.json'),'index':rec(ACCEPT/'index.html'),'all_pages':pages,'full_event_count':count_expected,'network_or_device_or_model_execution_performed':False});print('R10_RENDER_CANDIDATE_COMPLETE',count_expected,flush=True)
if __name__=='__main__':main()
