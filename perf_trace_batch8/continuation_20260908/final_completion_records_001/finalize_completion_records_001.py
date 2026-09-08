from pathlib import Path
import json, hashlib, datetime, shutil, subprocess
C=Path('/public/home/accl15ptg7/run_R08_R10'); P=Path('/public/home/accl15ptg7/auto_trace'); D=P/'perf_trace_batch8/continuation_20260908'; RUN=P/'perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003'
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def record(p):return {'path':str(p),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
remote=read(C/'FINAL_REMOTE_RELEASE_VERIFICATION_001.json');assert remote['status']=='complete' and remote['release_count']==16 and remote['asset_count']==79 and remote['all_expected_remote_assets_currently_present_with_exact_size_and_SHA256']
preview=read(C/'R10_readable_previews_001/READABLE_PREVIEWS_COMPLETE.json');assert preview['status']=='complete' and len(preview['pages'])==5
assert all(x['same_accepted_HTML_SHA256'] and not x['page_errors'] for x in preview['pages'])
watch_names={'publish_accepted_captures_004.py','watch_runtime_health_007.py','remote_checkpoint_watchdog_012.py'}
active=[]
for p in Path('/proc').iterdir():
 if p.name.isdigit():
  try:
   argv=(p/'cmdline').read_bytes().split(b'\0')
   if any(Path(x.decode(errors='replace')).name in watch_names for x in argv if x):active.append(p.name)
  except OSError:pass
assert not active,active
closure={'status':'closed','observed_utc':now,'matching_watchdog_processes_remaining':active,'stop_markers_present':all((C/n).exists() for n in ['STOP_ACCEPTED_CAPTURE_PUBLISHER','STOP_RUNTIME_HEALTH_WATCHDOG','STOP_REMOTE_CHECKPOINT_WATCHDOG']),'tool_session_exit_codes':{'accepted_capture_publisher_004_session_12763':0,'runtime_health_007_session_44834':143,'remote_progress_012_session_17524':143},'exit_code_source':'write_stdin completion results observed during finalization','normal_exit_claimed_for_health_and_progress_watchdogs':False,'note':'Stop markers requested after stage completion. Health/progress wrapper sessions reported 143; no normal exit or precise signal origin is inferred. All business stages and publications had already completed; final snapshot is run separately.'}
write(C/'FINAL_WATCHDOG_CLOSURE_001.json',closure)
stages={}
for st in ['R08','R09','R10']:
 h=RUN/'handoffs'/f'{st}.continuation.json'; assert read(h)['status']=='complete'
 pub=C/'publication'/f'complete_{st}'/'PUBLICATION_COMPLETE.json'; p=read(pub);assert p['status']=='published' and p['all_server_asset_sha256_match']
 stages[st]={'status':'complete','handoff':record(h),'publication_receipt':record(pub),'release_url':f'https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-{st.lower()}-complete-20260908'}
zip_asset=next(a for r in remote['releases'] for a in r['assets'] if a['name']=='R10_offline_acceptance.zip')
final={'status':'complete','verified_utc':now,'runtime_run_id':'batch8-dp2-fresh-003','additional_machine_time_required':False,'authorized_deadline_utc':'2026-09-09T04:18:09Z','stages':stages,'R08_accepted_captures':12,'planned_R08_captures':12,'trace_coverage':{'requests':8,'DP_ranks':2,'requests_per_rank':4,'scope':'R06-declared first prefill and first decode only','prefill_targets_per_request':784,'decode_targets_per_request':784,'process_targets_per_capture':12544,'all_captures_independently_audited':True,'all_1024_decode_phases_traced_claimed':False},'R10':{'actual_offline_browser_pages_passed':5,'main_timeline_events':59872,'main_plus_context_events':378722,'external_network_attempts':0,'offline_zip':zip_asset,'entrypoint_after_unzip':'acceptance/index.html','Chinese_readable_preview_receipt':record(C/'R10_readable_previews_001/READABLE_PREVIEWS_COMPLETE.json')},'remote_review':{'releases':16,'assets':79,'all_sizes_and_server_SHA256_match':True,'receipt':record(C/'FINAL_REMOTE_RELEASE_VERIFICATION_001.json')},'storage':{'new_R08_R10_outputs_logs_physical_NFS':True,'weight_shards_removed_after_all_captures_and_raw_publications':11,'removed_weight_bytes':55563022432,'restored_original_files':53,'restored_original_bytes':77001580022,'original_restore_root':'/root/R08_release_restored_after_capture_001','restoration_full_SHA256_verified':True,'NFS_free_bytes':shutil.disk_usage(C).free,'root_free_bytes':shutil.disk_usage('/root').free},'limitations':{'R07_original_native_controller_terminal_claimed':False,'R07_CPU_DB_analysis_completed_seconds':132.545,'R08_replay_timing_used_as_observed_R07_latency':False,'achieved_speedup_claimed':False,'shape_context_mismatches_and_unavailable_metrics_explicitly_preserved':True},'watchdog_closure':record(C/'FINAL_WATCHDOG_CLOSURE_001.json'),'final_progress_snapshot_pending':True}
write(C/'FINAL_COMPLETION.json',final);shutil.copy2(C/'FINAL_COMPLETION.json',D/'FINAL_COMPLETION.json')
x=read(C/'RECOVERY_STATE_NFS.json')
for k in ['scheduler_session','capture_session','progress_watchdog_session','accepted_capture_publisher_session','raw_storage_watchdog_session','complete_stage_publisher_session','runtime_health_monitor_session','active_cpu_suffix_session']:x[k]=None
x.update({'status':'complete','final_reviewed_utc':now,'current_capture':None,'current_capture_phase':'all_twelve_complete','current_CPU_stage':'complete','current_CPU_phase':None,'CPU_phase_status_reviewed_utc':now,'additional_machine_time_required':False,'temporary_release_eviction_enabled':False,'current_unrestored_evicted_file_count':0,'outer_extension_status':'all_work_complete_before_authorized_deadline','active_capture_scheduler_deadline_utc':None,'supplementary_readable_previews_status':'complete: five unchanged accepted HTML pages, zero external requests','R10_full_stage_publication_status':'complete, all 5 exact expected remote asset digests verified; upload cache removed','final_remote_release_count':16,'final_remote_asset_count':79,'all_final_remote_asset_sizes_and_SHA256_verified':True,'final_remote_verification':str(C/'FINAL_REMOTE_RELEASE_VERIFICATION_001.json'),'completed_watchdogs_stopped':True,'watchdog_closure_receipt':str(C/'FINAL_WATCHDOG_CLOSURE_001.json'),'final_completion_record':str(C/'FINAL_COMPLETION.json'),'final_progress_snapshot_status':'pending final one-shot push','last_reviewed_main_commit':subprocess.check_output(['git','-C',str(P),'rev-parse','HEAD'],text=True).strip(),'home_storage_available_gib':round(shutil.disk_usage(C).free/2**30,2),'root_storage_available_gib':round(shutil.disk_usage('/root').free/2**30,2)})
write(C/'RECOVERY_STATE_NFS.json',x);shutil.copy2(C/'RECOVERY_STATE_NFS.json',D/'RECOVERY_STATE_NFS.json')
Q=D/'final_completion_records_001';Q.mkdir(exist_ok=True)
for n in ['FINAL_WATCHDOG_CLOSURE_001.json','finalize_completion_records_001.py']:shutil.copy2(C/n,Q/n)
readme='''# R08 → R10 最终交付与恢复入口

R08、R09、R10 均已完成实际执行、独立审计及完整 handoff，并发布完整阶段 Release。2026-09-08 22:35 UTC 的最终 GitHub API 复核确认 16 个 Release、79 个资产的大小与服务端 SHA256 全部匹配。无需额外机器时间。最终凭证见 [FINAL_COMPLETION.json](FINAL_COMPLETION.json)，远端复核见 [final_remote_release_verification_001](final_remote_release_verification_001)。

## 直接查看结果

下载 [R10 离线报告 ZIP](https://github.com/cspool/auto_trace/releases/download/perf-trace-batch8-r10-complete-20260908/R10_offline_acceptance.zip)，解压后打开 `acceptance/index.html`。ZIP 为 394,557,919 字节，SHA256 为 `633afcad6e0089feb9bb80df05da358fb83d80730505d5de49e01baa2c253f1c`。五个页面均已通过实际 Chromium 离线验收，外部网络请求为零；完整时间线支持缩放、筛选和无截断区间检查。

- [R08 完整阶段 Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r08-complete-20260908)：资源分析、审计、失败证据与完整文件清单；已在各采集 Release 保存的原始文件通过精确成员清单引用。
- [R09 完整阶段 Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r09-complete-20260908)：全部 12 张分析表、代码、日志与独立审计。
- [R10 完整阶段 Release](https://github.com/cspool/auto_trace/releases/tag/perf-trace-batch8-r10-complete-20260908)：完整阶段归档、离线 ZIP、文件及资产校验清单。
- [中文可读预览](R10_readable_Chinese_previews_001/README.md)：补装中文字体后，用原始已验收 HTML 重新截图；五个页面字节与正式验收保持一致，原始浏览器证据未替换。

## 实际覆盖与结论边界

R08 的 12/12 组采集均通过独立原生 DB/PMC 归因审计，覆盖全部 8 个请求，DP2 两张卡各 4 个请求。按照 R06 声明的范围，每个请求首个 prefill 和首个 decode 各覆盖 784 个目标，每组共 12,544 个 process、23,660 个原生归属 kernel。这里不声称完整追踪全部 1024 个 decode 阶段。三种 PMC 模式共 6,912 项物理 dispatch 归属。

R09 完成全部 12 张分析表；R10 主时间线有 59,872 个事件，连同上下文共 378,722 个唯一事件。实际浏览器验收覆盖全部事件、八请求、1 ns 范围及 105 次精确历史状态检查。相关阶段凭证分别见 `R08_local_complete_001`、`R09_local_complete_001`、`R10_local_complete_001` 和 `R10_actual_browser_acceptance_001`。

R07 CPU DB 复核已在 132.545 秒内完成；旧长耗时与重复扫描及范围连接缺少索引有关。R07 原始历史原生控制器是否正常终止无法追认，所有后续材料保留此限制。只有 R07 原始时钟用于 observed 延迟；R08 重放时钟不替代它。资源 shape 上下文不一致、采样缺口及不支持的指标均保留明确状态；分析候选不等于已实现性能提升。

## 容器丢失后的恢复

主分支本目录保留阶段检查点、代码、审计、日志及发布凭证。[进度分支](https://github.com/cspool/auto_trace/tree/progress/batch8-continuation-20260908/perf_trace_batch8/progress/batch8-continuation-20260908) 保留执行期间约每 10 分钟的状态、代码与日志快照，并补交最终快照；已完成任务的周期监控现已停止。各阶段完整 Release 是大文件恢复来源。恢复时先读最终状态和 `PUBLICATION_COMPLETE.json`、`FILE_MANIFEST.json`、`ASSET_MANIFEST.json`、`SHA256SUMS`，按资产与成员的原始大小、SHA256 校验。

NFS 控制目录为 `/public/home/accl15ptg7/run_R08_R10`；运行目录为 `perf_trace_batch8/runtime/workflow01-10-fresh-e2e/batch8-dp2-fresh-003`。所有新 R08–R10 产物、代码及日志物理保存在 NFS。`/root/r08_continuation_001_bulk` 是通向 NFS 的别名，不是可删除的 root 副本。`/public/share/accl15ptg7` 与 `/work1/share/accl15ptg7` 在本容器中不存在或未挂载。

权重在 GPU 采集期间物理保留于 root。全部 12 组验收、发布并确认采集进程关闭后，按用户授权删除 11 个权重分片（55,563,022,432 字节），释放恢复空间。随后从 Release 完整恢复 53 个临时回收原始文件（77,001,580,022 字节），逐文件核验原始 SHA256，CPU 接续前再次全量核验。已授权的恢复文件位于 `/root/R08_release_restored_after_capture_001`，通过原规范路径链接访问；新阶段产物仍在 NFS。当前无需恢复权重或重新运行 GPU。

若原始恢复文件随容器丢失，按 `release_restoration_complete_001`、`raw/runtime_tools/release_restoration_001/COMPLETE.json` 及各分组清单恢复相同字节。`restore_all_R08_release_artifacts_002.py` 支持按已有凭证恢复；先核对原映射、空间与远端 SHA256，保留已封存验收材料，不能以失效链接冒充原始文件。

## 代码与执行凭证

采集冻结工具为 `raw/runtime_tools/revision_021` 和 `tools/analysis_008`；CPU 实际接续入口为 `run_closed_R08_to_R10_003.py`，采用 `prepare_stage_assignments_004.py` 与 `stage_tool_templates_003`。外层路径映射优化经过 233 个真实路径与 11 个异常场景校验，每份前序源文件仍完整校验 SHA256。工具模板本身不替代实际执行、独立审计及 handoff。

runtime021 在同一个 DP2/TP1 服务中为两个 GPU 工作进程分别使用原生 HIPProf 会话，保留原有两次预热和八个并发请求。两份原始 DB/CSV 与正常关闭凭证完整保留；合并 DB/CSV 明确标记为派生无损数据，并记录原始 SHA256 和逐行映射。第九项前五次失败及诊断也已保留并单独发布，不计为成功；底层共享采集器故障的精确内部原因仍未证明。

最终监控关闭记录见 `final_completion_records_001/FINAL_WATCHDOG_CLOSURE_001.json`。健康及进度监控的外层会话报告退出码 143，因此不声称二者正常退出；所有业务阶段、浏览器和发布器已先完成，最终快照单独执行。机器授权截止时间保留为 2026-09-09 04:18:09 UTC（已包含第二次追加的 8 小时）。
'''
(D/'RECOVERY_README.md').write_text(readme)
with (D/'LIVE_PROGRESS.md').open('a') as f:f.write('\n- '+now+': Final completion records consolidated: R08/R09/R10 complete, 16 Releases / 79 asset SHA256 checks passed, all five readable previews complete. No additional machine time required. Watchdogs no longer running; health/progress wrapper exit codes 143 preserved without claiming normal exit. Final one-shot progress snapshot follows.\n')
print('FINAL_RECORDS_READY',now,'stages',list(stages),'NFS_free_GiB',x['home_storage_available_gib'],'root_free_GiB',x['root_storage_available_gib'])
