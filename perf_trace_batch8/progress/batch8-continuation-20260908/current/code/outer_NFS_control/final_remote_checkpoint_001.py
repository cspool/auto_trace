from pathlib import Path
C=Path('/public/home/accl15ptg7/run_R08_R10')
source=(C/'remote_checkpoint_watchdog_012.py').read_text()
source=source[:source.index('while time.time()<DEADLINE:')]
old='每10分钟提交一次当前状态、代码和完整日志快照；Git历史保留旧检查点。当前代码模板明确标记为未执行，不能作为R09/R10完成证据。每个通过独立审计的R08采集另发原始数据Release。'
new='R08、R09、R10 已完成并发布；这是最终状态、代码与日志快照，周期监控已停止。Git 历史保留此前检查点。实际完成证据为各阶段 handoff、独立审计和完整 Release；历史工具模板本身不作为执行证据。'
assert source.count(old)==1
source=source.replace(old,new)
namespace={}
exec(compile(source,'<final-progress-snapshot>','exec'),namespace)
namespace['snapshot']()
