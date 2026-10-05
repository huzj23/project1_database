# 服务器 Git 快照兼容性补记

静态图片交付提交为 `7906b1b03e4726b20626055fa464861c5ce91efd`，已推送云端。

首次服务器独立快照归档遇到两个旧 Git 兼容问题：bundle 没有可用的 HEAD 引用，且服务器 Git 不支持 `-C`。这不涉及模型、图片、仿真和渲染，也不改变已经完成的本地及云端提交。

修订 `tools/v63/freeze_code_snapshot.py`：克隆时明确选择 main，随后使用绝对 `--git-dir` 和 `--work-tree`；每次快照要求新的 revision，拒绝覆盖。失败的初次快照目录原样保留，不删除、不重置。

最终运行是否成功，以项目目录 `log/V6.3_execution/server_snapshot_<commit前12位>_r2.json` 的生成记录为准。仅在独立 `code_snapshots/` 中新建版本库，不修改服务器项目根目录的现有工作树。
