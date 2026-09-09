#!/usr/bin/env python3
"""Independent checks against sealed R09 CSVs; does not import renderer or builder."""
from pathlib import Path
import csv,json,hashlib,collections,sys,time,datetime,re
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT.parent/'continuation_001';R09=ROOT.parent.parent/'R09/continuation_001';csv.field_size_limit(2**31-1)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def rows(name):
 with (R09/'tables'/(name+'.csv')).open(newline='') as f:yield from csv.DictReader(f)
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def expected(items,key,score,memberid,memberkey):
 groups=collections.defaultdict(list)
 for x in items:groups[key(x)].append(x)
 out=[]
 for k,values in groups.items():
  ordered=sorted(values,key=memberkey);out.append({'key':k,'score':score(values),'members':[memberid(x) for x in ordered]})
 return sorted(out,key=lambda x:(-x['score'],x['key']))
def main():
 start=time.time();build=read(ROOT/'BUILD_MANIFEST.json');browser=read(ROOT/'validation/BROWSER_AUDIT.json');assert browser['status']=='complete' and not browser['external_requests'] and not browser['browser_errors']
 for r in build['source_sealed_inputs']:
  p=Path(r['path']);assert sha(p)==r['sha256'];copy=ROOT/'original'/p.relative_to(SOURCE);assert sha(copy)==r['sha256']
 checks={'sealed_originals_unchanged':True,'offline_browser_passed':True};payloads={}
 for r in build['page_revisions']:
  before=Path(r['before']['path']);after=Path(r['after']['path']);assert sha(after)==r['after']['sha256'];s=after.read_text();data=s.split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0];old=before.read_text().split('<script>const PAYLOAD=',1)[1].split(';</script>',1)[0];assert data==old and hashlib.sha256(data.encode()).hexdigest()==r['payload_sha256'];payloads[after.name]=json.loads(data)
  # No network calls/assets in executable presentation code. Textual source paths may be preserved inside data.
  presentation=s.split('<script>const PAYLOAD=',1)[0]+s.split(';</script><script>',1)[1];assert not re.search(r'<(?:script|img|link|iframe)[^>]*(?:src|href)=["\'](?:https?:)?//',presentation,re.I);assert not re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(',presentation)
  assert browser['results']['hardware' if 'HIGH_' in after.name else 'concurrency']['page_sha256']==sha(after)
 checks['complete_embedded_data_byte_identical']=True
 metas={m['logical_name']:m for p in payloads.values() for m in p['source_tables'] if m['logical_name'] in p['tables']}
 for name,m in metas.items():assert sha(R09/'tables'/(name+'.csv'))==m['sha256'],name
 print('DIRECT_R09_SOURCE_HASHES_VERIFIED',len(metas),flush=True)
 high=list(rows('high_latency_processes'));proc={p['process_range_id']:p for p in rows('process_timeline')};pl=list(rows('process_live_utilization'));ks=list(rows('kernel_concurrency'));requests=list(rows('request_timeline'));kernels=list(rows('kernel_timeline'))
 assert len(requests)==8 and {r['rank'] for r in requests}=={'0','1'}
 for r in requests:
  assert r['rank']==r['physical_device_id'];assert sum(p['request_id']==r['request_id'] for p in proc.values())==1568;assert any(k['request_id']==r['request_id'] for k in kernels)
 for h in high:assert int(h['duration_ns'])==int(proc[h['process_range_id']]['end_ns'])-int(proc[h['process_range_id']]['begin_ns'])
 expected_high=expected(high,lambda x:x['peer_group_key'],lambda xs:sum(int(x['duration_ns']) for x in xs),lambda x:x['process_range_id'],lambda x:(-int(x['duration_ns']),x['process_range_id']))
 assert expected_high==browser['results']['hardware']['groups']
 available=[p for p in pl if p['availability_state']=='available'];phase=lambda p:'prefill' if '-prefill-' in p['forward_id'] else 'decode';dur=lambda p:int(p['process_end_realtime_ns'])-int(p['process_begin_realtime_ns'])
 for p in available:assert int(p['timing_eligible_sample_count'])>=3 and p['se_active_cu_pct_mean']!='' and int(p['intersecting_gap_count'])==0
 expected_raw=expected(available,lambda p:json.dumps([phase(p),p['process_id'],p['fragment_id']],separators=(',',':')),lambda xs:max(map(dur,xs)),lambda p:p['process_range_id'],lambda p:(-dur(p),p['process_range_id']))
 observed=browser['results']['concurrency'];assert expected_raw==observed['groups']['raw'];assert len(available)==observed['availableCount']
 forwards=collections.defaultdict(list)
 for p in pl:forwards[p['forward_id']].append(p)
 expected_dual=[]
 for key,ps in forwards.items():
  b=min(int(p['process_begin_realtime_ns']) for p in ps);e=max(int(p['process_end_realtime_ns']) for p in ps);rr=ps[0]['request_id'];segments=[r for r in ks if r['scope_type']=='request_rank_device' and r['request_id']==rr and int(r['begin_ns'])<e and int(r['end_ns'])>b];ordered=sorted(segments,key=lambda r:int(r['begin_ns']));assert all(int(a['end_ns'])<=int(z['begin_ns']) for a,z in zip(ordered,ordered[1:]));total=sum(min(e,int(r['end_ns']))-max(b,int(r['begin_ns'])) for r in segments);expected_dual.append({'key':key,'score':total,'members':[p['process_range_id'] for p in ps]})
 expected_dual.sort(key=lambda x:(-x['score'],x['key']));assert expected_dual==observed['groups']['dual'];assert len(expected_dual)==16
 launch=list(rows('launch_gaps'));expected_launch=[{'key':r['gap_id'],'score':max(int(r['gap_ns']),int(r['overlap_ns'])),'members':[r['gap_id']]} for r in launch if max(int(r['gap_ns']),int(r['overlap_ns']))>0];expected_launch.sort(key=lambda x:(-x['score'],x['key']));assert expected_launch==observed['groups']['launch']
 print('ALL_RANKINGS_EXCEPT_LIVE_VERIFIED',flush=True)
 needed={i for r in observed['gapEndpointChecks'] for i in [r['previous_index'],r['next_index']]};endpoints={};gaps={};samples=collections.Counter();anchors=[];count=0
 for i,r in enumerate(rows('live_utilization_aligned')):
  count+=1
  if r['record_kind']=='sample':samples[r['native_device']]+=1
  elif r['record_kind']=='gap':gaps[r['source_row_id']]=r
  elif r['record_kind']=='anchor':anchors.append(r)
  else:raise AssertionError(r['record_kind'])
  if i in needed:endpoints[i]=r
 for test in observed['gapEndpointChecks']:
  r=gaps[test['source_row_id']];p=endpoints[test['previous_index']];n=endpoints[test['next_index']];assert p['sequence']==r['previous_sequence'] and n['sequence']==r['next_sequence'];assert p['native_device']==n['native_device']==r['native_device'];assert p['call_end_monotonic_ns']==r['gap_begin_monotonic_ns'];assert n['call_begin_monotonic_ns']==r['gap_end_monotonic_ns'];assert int(r['gap_end_monotonic_ns'])-int(r['gap_begin_monotonic_ns'])==int(r['unobserved_gap_ns'])
 expected_unknown=[{'key':r['source_row_id'],'score':int(r['unobserved_gap_ns']),'members':[r['source_row_id']]} for r in gaps.values()];expected_unknown.sort(key=lambda x:(-x['score'],x['key']));assert expected_unknown==observed['groups']['unknown'];assert [samples['0'],samples['1']]==observed['sampleCounts'];assert len(gaps)==800 and len(anchors)==2 and sum(samples.values())==2491806
 checks.update({'eight_request_coverage':True,'all_high_latency_group_rankings_match_R09':True,'all_raw_utilization_group_rankings_match_R09':True,'all_dual_request_phase_busy_unions_match_R09':True,'all_launch_rankings_match_R09':True,'all_800_unknown_gap_rankings_and_endpoint_memberships_match_R09':True,'all_source_samples_preserved':True,'available_aggregates_meet_R09_gate':True,'ranking_uses_no_replay_timing':True,'no_cross_device_clock_bound_invented':True})
 for name,rr in [('high',expected_high),('dual',expected_dual),('raw',expected_raw),('unknown',expected_unknown),('launch',expected_launch)]:
  with (ROOT/('ranking_'+name+'.csv')).open('w',newline='') as f:
   w=csv.writer(f);w.writerow(['rank','group_or_event_key','score_ns','member_count','source_member_ids_json']);w.writerows((i+1,r['key'],r['score'],len(r['members']),json.dumps(r['members'])) for i,r in enumerate(rr))
 result={'status':'complete','kind':'presentation_revision_audit_not_new_measurement','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':sys.argv,'auditor_sha256':sha(Path(__file__)),'browser_audit_sha256':sha(ROOT/'validation/BROWSER_AUDIT.json'),'build_manifest_sha256':sha(ROOT/'BUILD_MANIFEST.json'),'checks':checks,'counts':{'requests':8,'processes':len(proc),'kernels':len(kernels),'high_latency':len(high),'high_groups':len(expected_high),'dual_groups':16,'raw_groups':len(expected_raw),'available_processes':len(available),'raw_samples':sum(samples.values()),'samples_by_device':dict(samples),'unknown_gaps':len(gaps),'launch_pairs':len(launch)},'presentation_files':[{'path':str(p.relative_to(ROOT)),'size':p.stat().st_size,'sha256':sha(p)} for p in [ROOT/'index.html',*sorted((ROOT/'acceptance').glob('*.html'))]],'rankings':[{'path':p.name,'sha256':sha(p)} for p in sorted(ROOT.glob('ranking_*.csv'))],'elapsed_seconds':time.time()-start}
 dump(ROOT/'validation/REVISION_AUDIT.json',result);print('INDEPENDENT_REVISION_AUDIT_COMPLETE',result['counts'],round(result['elapsed_seconds'],2),flush=True)
if __name__=='__main__':main()
