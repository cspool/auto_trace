# Batch8 DP2 容器丢失恢复检查点

每10分钟提交一次当前状态、代码和完整日志快照；Git历史保留旧检查点。当前代码模板明确标记为未执行，不能作为R09/R10完成证据。每个通过独立审计的R08采集另发原始数据Release。

恢复先读 `current/SNAPSHOT_MANIFEST.json` 和 `current/state/RECOVERY_STATE_NFS.json`（覆盖此前各版本状态），再核对 `current/r08/accepted` 与 `current/remote_publications`。只有原始数据、规范化清单和独立审计均匹配的采集才能复用；未完成采集只保留日志，不算通过。

截止时间：2026-09-08 20:18:09 UTC。
