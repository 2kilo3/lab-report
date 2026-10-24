# 验证说明

版本 2.0 基于公开版本 1.5 的固定提交 `f2b8b76167f029896bdda91b49cfc8fc82d1d567` 修改。验证日期：2026-10-22。它包含 Markdown 工作流与最小状态辅助器，不包含真实课程环境。

## 2.0 已做的检查

- 全量读取基线 17 个文件，保留写作五步、学术事实约束、环境路线与许可说明；逐项更新入口、参考文档、README、图示和行为场景，移除旧的强制小样、逐项摘要确认、固定英文字体及一律黑白表格规则。
- 运行 `python -B -m unittest discover -s tests -p 'test_*.py' -v`：19 项合成单元测试通过。覆盖未确认拒推进、当前审核绑定、改稿/意图/来源/证据/审核收据失效、局部回退与恢复、暂停不被改稿解除、新来源登记、坏状态/缺文件拒绝，以及 UTF-8 JSON 和中文带空格路径。
- 运行 Skill 创建工具的结构校验：通过。此结果仅检查入口结构等，不证明行为质量。
- 检查 Markdown 相对文件引用、UTF-8、缓存/临时文件及明显凭据模式；流程 SVG 重导 PNG 后目视核对文字与布局。静态检查不等于无漏洞或无隐私风险的全面保证。

## 验证边界

- 单元测试在当前 Linux / Python 环境执行，未在 Windows CP936、macOS、Claude Code、Codex、WorkBuddy 或 DeepSeek harness 各客户端做端到端安装/执行测试。跨平台设计不等于已跨平台实测。
- `tests/scenarios.md` 的 38 项是待执行行为测试设计，不能写成“38 项通过”。没有启动真实课程实验、独立客户端、完整实验报告试跑、Word/LibreOffice 版本矩阵或实际复杂模板往返测试。
- 状态辅助器检查文件版本和记录条件，不证明用户确认引用真实、审查上下文独立、审查质量或实验真实性；同权限改写记录不能由它阻止。它不是并发数据库、权限边界或自动 Agent 调度器。
- 版本 1.5 的历史静态扫描记录不构成本轮 2.0 的扫描结果；本轮未重跑 SkillSpector，不沿用其分数宣传当前安全性。

在实际任务中按 [环境与移植](../references/portability.md) 检查所需能力，并从当前候选做真实保存/重开/渲染。成功加载技能、状态单测通过、独立审查通过、用户验收和上传成功是不同结论。

## 2.0.1 窄更新验证

基于公开 main 提交 `9a8ccc6ba751967c51eeb36da1ade4867fc28f7b`，逐文件核对全部 20 个 Git blob 后保留完整基线。此次只补姓名目标的来源记录与最终人物元数据回读匹配证据，并加强原行为场景 17；不新增脚本、依赖或状态字段。README 与图示不变。

- 重新运行 19 项合成状态单元测试及 Skill 结构校验：通过；检查 UTF-8、相对链接和缓存文件：通过。
- 38 项行为场景仍为待执行设计；未实际修改、保存或转换真实报告，未实测 Word/PDF 的元数据写入。本次静态约束加强不等于上述行为已验证。

## 2.1.0 本轮实测

日期：2026-10-24，Windows、Python 3.12.10；从实际 main `bbea218da14131663e1e5bb09592877c0c70c324` 新建独立分支。开工前本轮实际运行原 19 项测试，全部通过，不沿用历史报告冒充基线。功能版本升 2.1.0，任务状态单向升级为 schema 2，保留原四类 artifact basis 与原动作守门。

| 层级 | 本轮结果与证据 |
| --- | --- |
| 静态检查 | 全部文本 UTF-8 可读；10 个 Python 文件通过 3.9 语法解析；Markdown 本地引用检查无缺失；git diff --check 通过；Skill 创建工具 quick_validate 在 UTF-8 模式通过。语法兼容不等于 Python 3.9 运行实测 |
| 单元及模拟集成 | `python -B -m unittest discover -s tests -p "test_*.py" -v`：59 项通过，保留原 19 项意义；新增经验协议 27、状态集成 11、宿主离线格式 2，均使用临时私有根，不访问生产经验库 |
| 多进程与故障模拟 | Windows 上 6 个并发采集进程同会话分片无丢更新；事务异常不切换登记表；尾行恢复、孤儿不激活、索引重建、旧备份撤销优先通过。非断电/网络盘完整认证 |
| 合成完整回放 | `python -B tests/replay_memory.py --output <独立目录>` 六步成功：事件/候选回顾→下次明确入口先读材料并展示→模拟用户核对确认→有效检索与实际采用/双重独审绑定→撤销后拒用旧审核→当前材料局部复核解除并重新独审。所有消息及核验身份明确标为 synthetic |
| 独立审查 | 两个无制作上下文的独立审查者读取完整原始要求、代码与测试。发现的范围放宽绕撤销、删除元数据残留、同批批准误伤、use 覆盖长期批准、共享会话增量及删除游标问题均修复，并独立定向复核闭环；未无限扩审 |
| 图示 | 更新 workflow、新增 memory-architecture；同一源生成 SVG/HTML、从 SVG 渲染 PNG，尺寸分别 1200×744 和 1200×800；两份 diagram self_check 通过，实际查看 PNG 无缺字/遮挡。蓝/橙/灰及文字标签一致 |
| 合成文档 | `tests/document_smoke.py` 配合 python-docx 和 LibreOffice 26.8.1.1：生成共享 Normal 样式、固定封面/评分表、两节的两页模板及经验 off/on 副本；只改允许区图题。保护区 XML/节属性未变，最终 DOCX 的 author、last_modified_by 均回读为 Synthetic Test Author。三份实际文件各渲染两页并逐页查看，无可见漂移、截断或重叠 |

文档测试仅是合成样例：两种开关的页面像素相同，固定第一页也与模板相同，第二页只呈现预期的图题居中。该结果不代表 Microsoft Word、WPS、真实课程模板、复杂公式或跨 Office 往返已通过。XML 检查与逐页观察分别执行，没有用结构检查替代视觉验收。可选文档测试不加入标准库测试依赖。

初次渲染因 LibreOffice 不在 PATH 失败，定位后仅为该子进程补已安装程序目录并重跑成功；没有安装应用或更改全局配置。Skill 校验器初次按系统 GBK 解码失败，明确以 `-X utf8` 重跑成功，没有改系统区域。开发中的失败用例先修实现再复跑，未删原断言、放宽门槛或伪填 not_applicable。

## 风险与可执行测试对应

| 风险 | 自动化覆盖 |
| --- | --- |
| 时序、身份、材料优先 | candidates_wait_for_next_explicit_begin、identity_resume_and_materials_first、end_only_saves_candidate_and_is_bounded、same_session_different_tasks_do_not_consume_each_other |
| 展示/确认绑定 | approval_requires_bound_host_check_and_subset、display_and_body_tampering_rejected、stale_selected_item_does_not_break_unrelated_subset；不宣称检测同权限完整伪造 |
| 状态、scope、污染、独立支持 | scope_and_hypothesis_and_unknown_dependency、self_cycle_and_authority_text_cannot_activate、source_file_drift_and_scope_mismatch_are_local、support_count_original_lineage_and_independent_runs |
| 可靠写入与恢复 | cross_process_same_session_collection、partial_tail_and_no_session_end_recovery、transaction_failure_leaves_registry_and_orphan_inactive、rebuild_never_activates_orphan_and_old_backup_cannot_revive |
| 迁移与旧收据 | migration_preserves_legacy_done_approval_and_receipt、invalid_unknown_or_missing_legacy_cannot_be_migrated、adoption_invalidates_even_without_artifact_change |
| 当前核查、关闭与去依赖 | revoked_authority_detected_with_unchanged_task_receipt、finish_holds_same_root_lock_through_done_write、off_does_not_remove_dependency_or_restore_old_review、root_identity_or_unavailability_denies_finish_but_detach_works、new_material_scope_rechecks_existing_adoption |
| 不误伤、不复活与删除 | use_preserves_long_term_approval、broader_scope_cannot_bypass_revocation、same_source_independent_existing_rule_survives_revoke、delete_keeps_other_item_approval_and_scrubs_verification_text、delete_preserves_unconsumed_batch_decision_for_other_item、import_does_not_inherit_active_without_current_sources |
| 宿主边界 | export_requires_clean_context_and_deduplicates 仅核对真实固定格式的合成样本；不能由 mock 推断默认注入已隔离 |

测试名在 tests/test_*.py，均有 test_ 前缀。原 38 项行为设计未改成通过，新增 39–50 同样为真实宿主 NOT EXECUTED；合成覆盖和真实人审/宿主验证分开。

## 尚未执行与能力边界

没有运行真实课程实验或真实报告对照，没有上传用户材料、静默安装插件/工具或修改其他任务全局配置。Claude Code、Codex、Cursor、DeepSeek harness 的原生生命周期、真实用户确认和 Claude Mem 自动注入隔离未端到端实测；只交付显式检查点和官方固定版本导出归一化。clean_context 是宿主核对责任声明，不能当技术隔离证明。未在 Linux/macOS/Python 3.9 运行；本机没有可用 WSL 分发，未为验证安装系统。

状态/经验脚本只能约束受控入口：不拦截同权限绕过写文件，不证明来源语义或独审质量，不保证不可原子化外部工具动作期间持续有效。相关撤销与 done 有同锁先后顺序；之后失效在下次入口识别，不能声称过去交付从未通过当时核查。

受控 restore 保留当前撤销，不从旧快照恢复 active/批准；但外部整根替换为内部一致旧快照是不可观测边界，仅靠根内状态无法保证发现。删除只清当前受管理内容，最小谱系标识仍可能被反查；不能保证清除外部副本、备份或模型已接收上下文，也不宣称同时彻底遗忘和永久防重导入。

| 效果指标 | 本轮记录 |
| --- | --- |
| 合成未批候选误采用、撤销绕交付、旧审核复用 | 回放断言均为 0；只代表这条可检查链路 |
| 合成保护区漂移、可见页面错误 | 0；仅上述两页样例及实际查看页面 |
| 真实报告证据漏项、模板漂移、页面错误与返工 | 未测，不能从合成结果外推 |
| 真实人工审核时间、总成本与效率收益 | 未测；回放只计脚本耗时，不计人工或模型成本，不宣称提效 |

新增经验数量不是效果指标。后续真实对照应在同一授权任务、模板和工具条件下分别记录上述质量与成本结果。
