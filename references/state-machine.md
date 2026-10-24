# 最小状态辅助器

实现：[scripts/workflow_state.py](../scripts/workflow_state.py)，Python 3.9+ 标准库。只读写本地工作记录及检查文件，不发起 Agent、实验、安装、联网或上传。

运行：`python -B scripts/workflow_state.py --state <任务目录/state.json> --request <请求.json>`。所有请求/结果 UTF-8 JSON；请求中的相对材料路径以 state 所在目录为基准。记录放任务工作目录，不放技能安装目录。stdout 一份 JSON，成功退出 0，检查/文件/JSON 错误退出 2。调用方以 `encoding="utf-8"` 解码。

## 动作

每个请求都有 `action`，附加字段如下：

- init：maker（制作上下文身份）、sources（原始材料路径数组，可以为空但不能遗漏真实已有材料）。现存状态禁止重新初始化。
- submit_intention：path（意图 MD）。仅 intake/awaiting_confirmation 可用，进入 awaiting_confirmation。
- confirm：message_ref（真实用户确认对话位置）。只可在待确认态使用；记录当前意图 SHA-256，进入 produce。工具不能验证这段引用是真的，宿主必须核实；绝不自动生成或将脚本成功当作授权。
- submit_draft：paths（当前候选成果路径数组，至少一项）、evidence（证据路径数组，按任务可为空）。仅 produce，进入 review。
- status：无其他字段。返回 phase、waiting_reason、basis（sources/intention/draft/evidence 的当前路径及摘要）。恢复前先调用；不是只显示过期标签。
- record_review：path（独审 JSON 收据）。仅 review；严格比对下述字段。
- finish：仅 review 且现有收据仍匹配全部材料及检查时进入 done。不代表已上传或用户已验收。
- rollback：to 为 intake/produce/review；reason 写具体问题、影响范围及回退依据。清除旧审核，保留所有成果文件。回 intake 同时撤销确认；其他回退不能跳过确认。未评估来源变化只允许回 intake，不因此消除待评估标记。
- pause：kind 为 blocked 或 failed；reason 必填。保存恢复阶段，blocked 表示等待输入/权限等，不冒称执行失败。
- resume：reason 写解除阻塞/修复依据；先查实际文件，不允许跳过来源影响评估。
- set_sources：paths（新的完整原始材料路径数组）、reason。登记新增或调整来源清单，清除审核并进入待评估 blocked。
- reassess：requirements_changed（布尔值）、reason（原始材料变更的影响依据）。仅检测到来源/清单变化后使用。若需求变化回 intake 并撤销确认；若已确认意图未改变回 produce，保留原用户确认但必须重新独审。不会要求无关内容重做。

## 独审收据 JSON

字段：reviewer（不同于 maker 的独审上下文身份）、context_ref（真实独立会话/进程引用）、basis（复制对当前产物执行 status 返回的完整 basis）、verdict（pass）、checks。

checks 必须包含 requirements、evidence、writing、format、render、final_file。每项是含 status 与 reason 的对象；status 只接受 pass 或 not_applicable，reason 必须非空。没有截图/无版面对象可据实标不适用，缺渲染能力或尚未检查不能写不适用。审核失败、未知、缺关键证据不允许完成；先按问题影响范围 rollback 修订，再交独审复核。收据是独审输出，不应由制作 Agent 为凑条件生成。

requirements、writing、final_file 必须 pass，不可标不适用；其余条件项不适用需真实原因，缺工具/未验证不是不适用。final_file 的 reason 应包含或定位到最终交付文件中适用人物元数据的回读记录，核对已确认姓名目标；不能仅写“作者已修改”。按 [文档输出](document-output.md) 记录实际值，软件生成器字段另行区分。仅审查输出为无人物元数据的纯文本等格式时说明这一事实，不虚构字段或改动作为来源的原报告。

这不是质量评估器：字符串不能证明独立性，非空理由不能证明检查质量，文件摘要不能证明证据真实。宿主须启动真实独审上下文并核对实际输出；同权限恶意改写状态无法由此脚本阻止。摘要用于后台版本绑定，不是报告里替代真实自然操作的截图。

## 变更与恢复

- 每次非 init 动作先校验状态结构、审批门和实际文件。来源变化进入 blocked 并需 reassess；意图变化撤销确认；证据变化回 produce；成稿变化回 review；以上均撤销旧审核，done 也不例外。
- 收据文件变化撤销审核并回 review；旧收据与新成稿 basis 不匹配会被拒绝。
- 缺文件、坏 JSON/结构不放行，不默默从零开始。恢复原文件；原始材料已被用户撤回时可用 set_sources 正式登记新清单并 reassess。禁止手改 phase/done 绕过。
- 外部权限/环境等 blocked/failed 暂停不会因成稿或来源变化自动解除；影响评估也保留外部暂停，须有真实解阻依据再 resume。
- 使用同目录临时文件、flush/fsync 和 os.replace 保存。不是数据库或多写者锁；同一任务仅一位编排者写状态。保留版本备份由任务工作目录管理，不能宣称断电/并发事务已完整验证。

## 审查完成不等于报告合格

制作/修改任务的 draft 是最终候选及本次要求的附属交付物，pass 必须对应实际完成标准。仅审查任务的 draft 是审查输出，原报告作为来源；独审可核实“已准确指出缺证”，据此完成审查任务，但绝不能把原报告说成合格。最终反馈必须区分这两种结论。用户仍有人工审看权，done 不表示用户已认可，也不表示上传成功。

## 最短使用顺序

1. 建工作目录，将各次 action JSON 保存在其中。init → submit_intention。
2. 用户确认实际意图后，confirm 填真实对话引用，开始授权范围内工作。
3. submit_draft 登记候选和证据。status 的 basis 交独审；独审检查原材料、意图与成稿后写收据。
4. record_review → finish。失败则按具体问题 rollback、修复、重新审查。不修改 JSON 强推状态。
5. 中断恢复先 status；缺 Python 时沿本文件同样的状态和守门条件手工记录，明确未使用可执行校验器。

例：确认请求为 `{"action":"confirm","message_ref":"实际确认消息的可定位引用"}`。状态工具不会查询或验证该消息，调用者必须先检查用户确实确认了当前意图，示例不能作为授权。

测试命令：`python -B -m unittest discover -s tests -p 'test_workflow_state.py' -v`。这些是合成状态逻辑测试，不是课程实验、文档排版或多 Agent 质量证明。

## 2.1 的 schema 2 与经验接线

功能版本为 2.1.0，任务 schema 为 2，经验 registry 自有 schema 1，三者分别管理。`basis()` 仍只含 sources、intention、draft、evidence。state.events 是任务动作日志，collection_events 是私有根采集日志；state.approval 是意图确认，memory_approval 是经验批准。

新增 task_id、session_ref、invocation_id、memory_mode、lessons_used、lessons_receipt、adoption_generation、memory_impact_pending、lessons_history、memory_checkpoint。新建及旧任务升级默认 memory_mode=off、空采用清单、代数 0；关闭且无依赖不访问根。开启是可选的显式设置，不改变原动作的确认/独审要求。任务仍只允许一个编排者写。

旧 schema 1 先按旧规则验证并检查实际文件，再在内存补默认字段、验证 schema 2 后原子提交；旁存原始 `state.json.schema1.bak`，不覆盖已有备份。合法且工件未变的旧 done 保持 done，原确认、artifact basis 与独审收据不改写。坏状态、未知 schema、缺失文件不会通过补字段洗白。迁移入口是 migrate，也可在原动作读取时升级；显式使用 migrate 便于先检查备份。旧脚本会拒绝 schema 2；升级后只用新写者，备份恢复只在停止写入并确认没有新进度时进行，不混用脚本或倒改 schema。

调用时可用 `--memory-root` 指定测试根；通常由 LAB_REPORT_MEMORY_HOME/平台默认定位。根在一次入口内固定。[经验协议](memory.md) 说明字段、审批、失效、删除和恢复。

| 新动作 | 请求及守门 |
| --- | --- |
| memory_mode | mode 为 on/off；off 保留采用历史和代数，不能解除实际依赖 |
| memory_begin | mode=on；先读材料，再提交 host、native_session_id/session_token、explicit_use_ref、materials_read:{refs,constraints}；任务 ID 取 state；resume 时带原 invocation_id |
| memory_checkpoint | status 为 saved/unavailable/disabled，source_ref 为最小恢复指针；不复制长期正文 |
| adopt_lesson | 已确认意图，produce/review/done；lesson:{id,revision}，application:{action,affected:[对象或页面]}。先查权威根，再登记待操作依赖，返回 application_id |
| record_application | application_id、真实 result（不可为 pending）；补记外部工具实际结果。存在 pending 应用不能独审交付 |
| refresh_lessons | 在线重查实际依赖并刷新收据；不等于重新人审 |
| acknowledge_memory_recovery | reason；在线核查恢复后的同一已批准内容，清影响标记，仍须当前代数独审；用户暂停需先在经验根明确 resume |
| detach_lessons | 明确 lessons:[{id,revision}] 与独立局部复核 JSON path；绑定当前 basis、原 lessons_basis、目标 applications_digest、reviewer/context_ref、verdict=pass、reason 和 revalidated_from_current_materials:true |
| migrate | 验证、备份并单向升级；不伪造新审核 |

每次 status/原动作先 reconcile 文件并在线 check_used 已采用经验；record_review 和 finish 同样执行，不能凭上次收据离线放行。stdout 保留原字段，新增身份、lessons_basis、adoption_generation、lessons_used、lessons_receipt 与影响清单。lessons_receipt 含 task/root/basis、所查依赖状态版本、时间、结果与自身摘要；在线重查未变可重建收据，时间变化不导致独审失效。

独审 JSON 增加 lessons_basis（status 返回的字符串），记录实际读过的采用清单。只有空清单且 adoption_generation=0 可接受不含此字段的旧收据；经历采用再解除的空清单仍需新格式。新增应用、补记结果、替换/解除依赖、首次发现失效均递增代数并清旧审核；重复同一未解决失效不递增。核查时间和无关库更新不进摘要，纯方法变动保留意图确认。

相关经验被撤销/替代、来源漂移、错根或不可读时，记录影响并使旧审核失效；已 done 的后续失效另记 after_delivery，不改历史交付文件。关闭后仍有依赖必须检查。库离线时可按当前原材料修订/复核受影响部分，再用 detach_lessons 消费绑定当前成果的独立复核记录、移除实际依赖并重新独审；不能以切开关冒充无记忆完成。

finish 从权威根同一 OS 互斥的短临界区内复查依赖、重读原独审收据并原子写 done。撤销先提交则不放行；done 先提交则之后撤销在下一受控入口识别。这只串行化规定入口，不拦截同权限绕过入口的文件改写，也不保证外部工具操作期间持续实时有效。
