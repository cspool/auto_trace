"""Independent R10 terminal audit: reconstruct from sealed R09 CSV, never renderer."""
from pathlib import Path
from decimal import Decimal
import csv,json,hashlib,collections,gzip,base64,itertools,time,sys,re
csv.field_size_limit(2**63-1)
ROOT=Path(__file__).parents[2];ACCEPT=ROOT/'acceptance'
NAMES=['request_timeline','process_timeline','kernel_timeline','live_utilization_aligned','process_live_utilization','kernel_concurrency','queue_concurrency','launch_gaps','high_latency_processes','dependency_state','traffic_resource_attachment','opportunity_candidates']
def check(v,m):
 if not v:raise RuntimeError(m)
def read(p):return json.loads(Path(p).read_text())
def rows(p):
 with Path(p).open(newline='') as f:yield from csv.DictReader(f)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def js(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(js(v).encode()).hexdigest()
def check_record(x):
 p=Path(x['path']);check(p.is_absolute() and '..' not in p.parts,'exact absolute source path');check(p.stat().st_size==x['size'] and sha(p)==x['sha256'],'file hash and size: '+str(p))
def payload(path):
 text=path.read_text();prefix='<script>const PAYLOAD=';start=text.index(prefix)+len(prefix);end=text.index(';</script>',start);encoded=text[start:end];return json.loads(encoded),encoded,text

def main():
 started=time.monotonic();checks={};assignment=read(ROOT/'authorization/assignment.json');check(assignment['runtime_goal']=='R10' and assignment['predecessor_stages']==['R%02d'%i for i in range(1,10)],'exact R01-R09 assigned prefix')
 for item in assignment['predecessor_handoffs']+assignment['consumed_sources']+[assignment['cumulative_runtime_ledger']]:check_record(item)
 expected_stages=['R%02d'%i for i in range(1,10)]
 for stage,item in zip(expected_stages,assignment['predecessor_handoffs']):
  h=read(item['path']);check(h['runtime_goal']==stage and h['runtime_run_id']==assignment['runtime_run_id'] and h['trace_profile_sha256']==assignment['trace_profile_sha256'],'same-run predecessor identity')
  if stage=='R07':check(h['status']=='complete_recovered_offline' and not h['native_controller_lifecycle_completion_claimed'] and not h['remote_original_hipprof_terminal'],'explicit immutable offline recovery exception')
  else:check(h['status']=='complete' and h['evidence_status']=='complete' and h['coverage_target_met'],'complete prefix admission')
 manifest=read(ACCEPT/'full_timeline_manifest.json');analysis=read(assignment['r09_analysis']['path']);check_record(assignment['r09_analysis']);metas={r['logical_name']:r for r in analysis['tables']};check(list(metas)==NAMES,'exact ordered twelve-table surface');check(manifest['r09_tables']==analysis['tables'],'renderer exact accepted table schemas')
 for meta in metas.values():
  check_record(meta)
  with Path(meta['path']).open(newline='') as f:
   reader=csv.DictReader(f);check(reader.fieldnames==meta['schema'],'ordered schema');count=sum(1 for _ in reader)
  check(count==meta['row_count'] and digest(meta['schema'])==meta['schema_sha256'],'complete source row count/schema hash')
 requests={r['request_id']:r for r in rows(metas['request_timeline']['path'])};processes={r['process_range_id']:r for r in rows(metas['process_timeline']['path'])};kernels={r['kernel_instance_id']:r for r in rows(metas['kernel_timeline']['path'])}
 check(len(requests)==8 and {x['rank'] for x in requests.values()}=={'0','1'},'eight measured DP2 requests');check(all(r['rank']==r['physical_device_id'] for r in requests.values()),'exact physical topology');check(max(int(r['begin_ns']) for r in requests.values())<min(int(r['end_ns']) for r in requests.values()),'all eight concurrent request intervals')
 for q in manifest['batch8_coverage']['coverage']:
  ps=[p for p in processes.values() if p['request_id']==q['request_id']];ks=[k for k in kernels.values() if k['request_id']==q['request_id']];check(len(ps)==q['process_targets'] and len(ks)==q['strict_owned_kernels'],'all eight exact per-request universes')
  for phase in q['phases']:check(sum(p['phase']==phase['phase'] for p in ps)==phase['observed_process_targets'],'every request-phase retained')
 origin=min(int(r['begin_ns']) for r in requests.values());check(str(origin)==manifest['origin_ns']==manifest['request_begin_ns'],'measured envelope integer origin');expected=len(requests)+len(processes)+2*len(kernels);check(expected==manifest['expected_event_count'],'source event formula')
 check_record(manifest['perfetto']);trace=json.loads(Path(manifest['perfetto']['path']).read_text(),parse_float=Decimal);events=trace['traceEvents'];check(len(events)==expected,'complete Perfetto event count');seen=collections.Counter();pairs=collections.defaultdict(list);classes=collections.Counter();lanes=collections.defaultdict(list)
 for event in events:
  check(event['ph']=='X','exact interval display record');a=event['args'];kind=event['cat'];sid=a['source_row_id'];check(kind in ['request','process','strict_owned_kernel','gpu_queue'],'only declared event classes');source=requests if kind=='request' else processes if kind=='process' else kernels;check(sid in source,'source row identity exists');r=source[sid];b=int(r['begin_ns']);e=int(r['end_ns']);rb=int(requests[r['request_id']]['begin_ns']);table='request_timeline' if kind=='request' else 'process_timeline' if kind=='process' else 'kernel_timeline'
  check(a['original_row']==r and a['source_row_sha256']==digest(r),'complete original source row and canonical hash');check(a['source_table']==table and a['source_table_sha256']==metas[table]['sha256'],'exact source table identity');check(a['absolute_begin_ns']==str(b) and a['absolute_end_ns']==str(e) and a['duration_ns']==str(e-b),'absolute decimal observed times');check(a['relative_begin_ns']==str(b-origin) and a['relative_end_ns']==str(e-origin) and a['request_relative_begin_ns']==str(b-rb) and a['request_relative_end_ns']==str(e-rb),'lossless exact relative coordinates');check(Decimal(event['ts'])*1000==b-origin and Decimal(event['dur'])*1000==e-b,'Perfetto decimal coordinate precision');check(a['request_id']==r['request_id'] and a['rank']==r['rank'] and a['native_device']==r['physical_device_id'],'event request/rank/device');check(a['evidence_class']=='observed_r07_timing','sole observed latency source');check(a['observed_interval_sha256']==digest([sid,str(b),str(e)]),'observed interval pair digest')
  check(a['display_copy_index']==(1 if kind=='gpu_queue' else 0),'deterministic display copy index');check(a['paired_kernel_display_copies_non_additive']==(kind in ['strict_owned_kernel','gpu_queue']),'display copies cannot double time');check(isinstance(a['overlap_sub_lane'],int) and a['overlap_sub_lane']>=0,'explicit overlap lane');check(event['tid']==a['base_track']+'/lane:'+str(a['overlap_sub_lane']),'exact lane track identity');lanes[kind,a['base_track']].append((b,e,sid,a['overlap_sub_lane']));classes[kind]+=1;seen[kind,sid]+=1
  if kind in ['strict_owned_kernel','gpu_queue']:pairs[sid].append(a)
 for kind,source in [('request',requests),('process',processes),('strict_owned_kernel',kernels),('gpu_queue',kernels)]:check({sid for (k,sid),n in seen.items() if k==kind}==set(source) and all(seen[kind,sid]==1 for sid in source),'every source event exactly once in class')
 for kid,pair in pairs.items():check(len(pair)==2 and pair[0]['observed_interval_sha256']==pair[1]['observed_interval_sha256'],'paired immutable kernel interval')
 for key,items in lanes.items():
  ends=[]
  for b,e,sid,lane in sorted(items):
   expected_lane=next((i for i,end in enumerate(ends) if end<=b),len(ends));check(lane==expected_lane,'independently deterministic half-open overlap lane')
   if lane==len(ends):ends.append(e)
   else:ends[lane]=e
 check(dict(classes)==manifest['event_class_counts'],'exact manifest class counts');checks['perfetto_conservation']={'counts':dict(classes),'total':expected,'unique_kernel_pairs':len(pairs),'source_row_fields_all_equal':True,'decimal_nanoseconds_exact':True,'overlap_lanes_recomputed':True};del trace,events
 pages=[];legends=['observed R07 timing','observed live utilization','replay_projected R08 hardware attributes','derived analysis','unavailable/unknown evidence']
 for page in manifest['pages']:
  check_record(page);p=Path(page['path']);check(p.parent==ACCEPT,'contained accepted page');data,encoded,html=payload(p);check(hashlib.sha256(encoded.encode()).hexdigest()==page['embedded_payload_sha256'],'embedded data bytes');check(data['origin_ns']==str(origin) and data['coverage']==manifest['batch8_coverage']['coverage'],'page exact source origin/coverage');check(all(label in html for label in legends),'textual evidence class legends');check(data['source_tables']==analysis['tables'],'all twelve sealed source table descriptions');counts={}
  for name,pack in data['tables'].items():
   meta=metas[name];check(pack['row_count']==meta['row_count'] and pack['source_table_sha256']==meta['sha256'] and pack['original_schema']==meta['schema'],'embedded complete table contract');check(set(pack['fields']).isdisjoint(pack['constants']) and set(pack['fields'])|set(pack['constants'])==set(meta['schema']),'lossless constant-column factorization');original=iter(rows(meta['path']));digest_rows=hashlib.sha256();n=0
   for block in pack['blocks']:
    chunk=json.loads(gzip.decompress(base64.b64decode(block,validate=True)))
    for values in chunk:
     check(len(values)==len(pack['fields']),'complete packed row width');restored={**pack['constants'],**dict(zip(pack['fields'],values))};raw=next(original,None);check(raw==restored,'every source string cell losslessly retained: '+name);digest_rows.update((js([raw[f] for f in meta['schema']])+'\n').encode())
     if name in ['request_timeline','process_timeline','kernel_timeline']:check(pack['source_row_hashes'][n]==digest(raw),'page original source row hash')
     n+=1
   check(next(original,None) is None and n==meta['row_count'] and digest_rows.hexdigest()==pack['canonical_rows_sha256'],'no tail deletion, row merge, sample, or event cap');counts[name]=n
  check(counts=={n:x['row_count'] for n,x in page['embedded_tables'].items()},'page manifest complete embedded universes');pages.append({'path':str(p),'all_rows_and_cells_checked':counts,'all_evidence_legends':True});print('AUDIT_R10_PAGE_LOSSLESS',p.name,flush=True)
 checks['full_embedded_content']=pages
 browser=read(ROOT/'validation/BROWSER_ACCEPTANCE.json');check(browser['status']=='complete' and browser['runtime_goal']=='R10' and browser['network_attempt_count']==0 and not browser['attempted_requests'] and browser['all_browser_processes_closed_before_result'],'completed network-denied browser run');check_record(browser['browser_binary']);check_record(browser['harness']);check_record(browser['full_timeline_manifest']);check(len(browser['pages'])==5 and all(not p['console_errors'] and not p['page_errors'] and not p['external_requests'] for p in browser['pages']),'all pages offline without errors')
 timeline=next(p for p in browser['pages'] if p['page']['path'].endswith('E2E_PROCESS_TIMELINE_LOSSLESS.html'))['checks'];check(timeline['full_universe']['main']==expected and timeline['full_universe']['source_lookup_all_pass'] and timeline['full_universe']['nonoverlap_lanes'],'complete browser original event lookup');check(timeline['exact_history']['states']>=100 and timeline['exact_history']['span_ns']=='1' and timeline['exact_history']['back_forward_exact'],'at least100 exact history states and1ns');check(not timeline['unbounded_interval_inspection']['result_cap'] and timeline['unbounded_interval_inspection']['density_preserves_all'],'unbounded inspection and reversible density');check(all(timeline['visible_pointer_and_jump_controls'].values()),'actual zoom pan box click and exact jump');checks['browser_independent_results']=browser
 offline=read(ACCEPT/'offline_acceptance_manifest.json');check(offline['status']=='complete' and offline['evidence_status']=='complete','offline manifest passed');check_record(offline['browser_acceptance']);check(offline['event_count']==expected and offline['network_attempt_count']==0,'offline exact event/network denominators')
 for item in offline['presentation_payload']:check_record(item)
 lineage=read(ROOT/'R10_SOURCE_LINEAGE.json');check(lineage['predecessor_stages']==expected_stages and lineage['predecessor_handoffs']==assignment['predecessor_handoffs'],'source lineage exact ordered prefix');check_record(lineage['offline_acceptance_manifest']);check(lineage['r09_analysis']==assignment['r09_analysis'],'R09 accepted analysis lineage');check(lineage['observed_clock_source']=='R07 only' and not lineage['replay_timing_used_as_latency'],'lineage clock separation')
 for key in ['model_execution_performed','gpu_dcu_execution_performed','device_query_performed','profiler_execution_performed','trace_collection_performed','pmc_collection_performed','replay_performed','external_network_contacted','target_mutation_performed','predecessor_mutation_performed','successor_execution_performed']:check(lineage['execution_boundaries'][key] is False,'CPU-only R10 boundary '+key)
 artifact=read(ROOT/'artifact_manifest.preaudit.json')
 for item in artifact['files']:check_record(item);check(Path(item['path']).is_relative_to(ROOT) and '/handoffs/' not in item['path'],'stage-only artifact manifest containment')
 required=[ACCEPT/x for x in ['index.html','E2E_PROCESS_TIMELINE.html','E2E_PROCESS_TIMELINE_LOSSLESS.html','HIGH_LATENCY_PROCESS_HARDWARE_TIMELINE.html','CONCURRENCY_UTILIZATION.html','E2E_PROCESS_TIMELINE.full.perfetto.json','full_timeline_manifest.json','offline_acceptance_manifest.json']]+[ROOT/'R10_SOURCE_LINEAGE.json'];check({str(p) for p in required}<={x['path'] for x in artifact['files']},'nine exact pre-audit deliverables sealed');check(offline['completion_audit_declared_path']==str(ROOT/'R10_COMPLETION_AUDIT.json'),'tenth required audit path')
 for item in offline['navigation_graph']:
  target=Path(item['resolved_target']);check(target.is_relative_to(ROOT) and (target.exists() or target==ROOT/'R10_COMPLETION_AUDIT.json'),'closed navigation graph with current audit sole deferred node')
 for key in ['complete_timeline','formal_r09_r10_regeneration']:check(manifest[key] is True,'literal complete timeline contract')
 check(manifest['sampling_performed'] is False and not manifest['top_n_or_event_cap'] and not manifest['replay_timing_used_as_latency'],'no sampling cap or replay latency')
 result={'schema_version':1,'status':'complete','execution_status':'complete','evidence_status':'complete','coverage_target_met':True,'next_authorization_required':False,'runtime_goal':'R10','runtime_run_id':assignment['runtime_run_id'],'lineage_id':assignment['runtime_run_id'],'trace_profile_sha256':assignment['trace_profile_sha256'],'independent_audit':True,'renderer_imported':False,'all_eight_requests_have_exact_trace_coverage':True,'event_count':expected,'checks':checks,'predecessor_handoffs':assignment['predecessor_handoffs'],'cumulative_runtime_ledger':assignment['cumulative_runtime_ledger'],'source_lineage_sha256':sha(ROOT/'R10_SOURCE_LINEAGE.json'),'preaudit_artifact_manifest_sha256':sha(ROOT/'artifact_manifest.preaudit.json'),'offline_acceptance_manifest_sha256':sha(ACCEPT/'offline_acceptance_manifest.json'),'full_timeline_manifest_sha256':sha(ACCEPT/'full_timeline_manifest.json'),'auditor_sha256':sha(Path(__file__)),'argv':sys.argv,'cpu_only':True,'replay_timing_used_as_latency':False,'elapsed_seconds':time.monotonic()-started}
 result['cumulative_runtime_ledger_sha256']=assignment['cumulative_runtime_ledger']['sha256']
 for stage,item in zip(expected_stages,assignment['predecessor_handoffs']):result[stage.lower()+'_handoff_sha256']=item['sha256']
 with (ROOT/'R10_COMPLETION_AUDIT.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print('R10_INDEPENDENT_COMPLETION_AUDIT_COMPLETE',round(time.monotonic()-started,2),flush=True)
if __name__=='__main__':main()
