# Batch8 DP2 容器丢失恢复检查点

R08、R09、R10 已完成并发布；这是最终状态、代码与日志快照，周期监控已停止。Git 历史保留此前检查点。实际完成证据为各阶段 handoff、独立审计和完整 Release；历史工具模板本身不作为执行证据。

恢复先读 `current/SNAPSHOT_MANIFEST.json` 和 `current/state/RECOVERY_STATE_NFS.json`（覆盖此前各版本状态），再核对 `current/r08/accepted` 与 `current/remote_publications`。只有原始数据、规范化清单和独立审计均匹配的采集才能复用；未完成采集只保留日志，不算通过。

截止时间：2026-09-09 04:18:09 UTC（已包含第二次追加的 8 小时）。
