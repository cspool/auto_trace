from pathlib import Path
P=Path('/root/r08_emergency_tools/stage_tool_templates/shared_001/cpu_stage_common.py')
s=P.read_text();begin=s.index('def validate_path(value):');end=s.index('def verify(item):',begin)
new='''def directory_mappings():
 maps={RUN/'artifacts'/('R%02d'%i):Path('/dev/shm/r08_continuation_predecessors/artifacts')/('R%02d'%i) for i in range(1,7)}
 for stage in ['R08','R09','R10']:
  sroot=RUN/'artifacts'/stage/'continuation_001';auth=sroot/'authorization/bulk_storage_authorization.json'
  if auth.exists():
   a=read(auth);check(a['runtime_goal']==stage and a['runtime_run_id']==RUN_ID,'bulk stage/run identity')
   for lexical,dest in a['paths'].items():
    lexical=Path(lexical);dest=Path(dest);check(lexical.is_relative_to(sroot) and dest.is_relative_to(Path('/root')),'explicit stage bulk roots');maps[lexical]=dest
 return maps

def storage_mappings():
 original,records=memory_mappings();maps={p:{**v,'destination_path':v['resolved_destination']} for p,v in original.items()}
 recovery=RUN/'artifacts/R08/continuation_001/raw/runtime_tools/storage_recovery_002/STORAGE_RECOVERY_COMPLETE.json';x=read(recovery);check(x['status']=='complete' and x['all_canonical_paths_resolve_identical_bytes'],'completed exact quota recovery');records.append(rec(recovery))
 for item in x['file_relocations']:
  check(item['same_bytes'] and item['source_content_not_changed'] and item['canonical_link_restored'],'immutable relocation');key=Path(item['source_path']);check(key not in maps,'unique relocation source');maps[key]=item
 folder=RUN/'artifacts/R08/continuation_001/raw/runtime_tools/published_storage_maps_001'
 for path in sorted(folder.glob('*.complete.json')):
  x=read(path);auth=path.with_name(path.name.replace('.complete.json','.authorization.json'));a=read(auth);check(x['status']=='complete' and x['canonical_link_verified'] and not x['new_measurement_or_content_change'],'closed accepted same-byte map')
  check(all(x[k]==v for k,v in a.items() if k!='status'),'authorization completion equality');receipt=x['prior_remote_publication'];check(sha(receipt['path'])==receipt['sha256'],'prior remote receipt bytes');remote=read(receipt['path']);check(remote['status']=='published' and remote['all_server_asset_sha256_match'],'remote verified before offload');records.extend([rec(auth),rec(path),rec(Path(receipt['path']))]);key=Path(x['source_path']);check(key not in maps,'unique accepted relocation');maps[key]=x
 return maps,records

def validate_path(value):
 p=localize(value);directories=directory_mappings();files,_=storage_mappings()
 def rebind_directory(q):
  for lexical,dest in directories.items():
   if q.is_relative_to(lexical):
    check(lexical.is_symlink() and os.readlink(lexical)==str(dest),'exact authorized directory symlink');return dest/q.relative_to(lexical)
  return q
 # File authorization uses logical source names; compare at the actual parent
 # after the explicitly listed directory mapping, never a general resolve.
 normalized={rebind_directory(k):v for k,v in files.items()}
 check(len(normalized)==len(files),'unambiguous normalized file map')
 check(p.is_relative_to(PROJECT) or p.is_relative_to(CONTROL) or p in files or any(p.is_relative_to(d) for d in directories.values()),'explicit source owner')
 q=rebind_directory(p);seen=set()
 while q in normalized:
  check(q not in seen,'no storage relocation cycle');seen.add(q);item=normalized[q];dest=Path(item['destination_path']);check(q.is_symlink() and os.readlink(q)==str(dest),'exact authorized file symlink');check(q.stat().st_size==item['size'],'relocated file size');q=dest
 check(p.resolve()==q and not q.is_symlink(),'no unlisted path or nested symlink');return p
'''
s=s[:begin]+new+s[end:];compile(s,str(P),'exec');P.write_text(s)
p=P.parent.parent/'r09_001/stage_common.py';s=p.read_text();b=s.index('def validate_source(p):');e=s.index('def verify(x):',b);s=s[:b]+'''def validate_source(p):
 from cpu_stage_common import validate_path
 validate_path(p)
'''+s[e:];b=s.index('def source_state():');e=s.index('def admission():',b);s=s[:b]+'''def source_state():
 from cpu_stage_common import target_state
 return target_state()
'''+s[e:];compile(s,str(p),'exec');p.write_text(s)
p=P.parent.parent/'r10_001/browser_acceptance.py';s=p.read_text().replace("flags=['--disable-background-networking'", "flags=['--disable-gpu','--disable-gpu-compositing','--disable-gpu-rasterization','--disable-background-networking'");compile(s,str(p),'exec');p.write_text(s)
print('EXACT_STORAGE_VALIDATOR_TEMPLATE_PREPARED')
