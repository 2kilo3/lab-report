# 受人工监督的经验协议

Memory 管存储、查询与治理；Self Improvement 管采集、整理、人审、应用及反馈，共用本协议和一个权威根。运行经验只作为受控方法上下文，不改 SKILL.md、系统指令、模板、权限或验收规则。原五段流程及模板保护、当前真实证据、独审、最终页面和人物元数据回读仍为硬门槛。

## 根、身份与事务

`LAB_REPORT_MEMORY_HOME` 指定私有根。未设置时，Windows 为 `~/.lab-report/memory`；类 Unix 为 `$XDG_STATE_HOME/lab-report/memory`，未设置 XDG 时为 `~/.local/state/lab-report/memory`。每次入口解析，事务内固定路径和 root_id。测试显式传临时根，不访问生产库。技能目录和 Git 仓库中的根会被拒绝；主编排者另须排除课程提交目录和任务目录，CLI 无法自动识别任意目录的业务用途。

路径权限沿宿主约束，不擅改全局配置、不偷偷另建根。无依赖且关闭时不访问经验根。无依赖且库不可用时，主编排者记录 `memory_checkpoint` 的 unavailable 与来源指针，继续原流程；已经采用的任务必须在线核查或完成解除依赖。

| 位置 | 含义 |
| --- | --- |
| registry.json | 唯一权威：状态、有效头、批准、来源映射、依赖、治理沿革和撤销标识 |
| sessions/<内部会话 ID>/collection_events.jsonl | 按会话追加的采集日志，用于增量整理与恢复 |
| sessions/<ID>/recap-*.md | 六栏目回顾：时间、任务场景、关键决策、问题与解决、可复用经验、待优化项 |
| lessons/<id>/<revision>.md | 七栏目不可变正文：条件、问题、方法、观察结果、证据、验证办法、不适用情形 |
| playbooks/<id>/<revision>.md | 相同治理下的组合方法，绑定具体依赖修订 |
| reviews/ | 不可变展示及宿主核对确认记录 |
| INDEX.md、experience.md | 可重建的短索引与六栏目总览；不能直接作为有效规则加载 |

task_id 标识跨会话报告任务；session_ref 由宿主命名空间与原生 ID 组成，缺原生 ID 时显式生成并保留 session_token；invocation_id 标识一次明确技能使用及其恢复链。不可用 maker、任务目录时间或 CLI 进程启动推断会话。`begin` 固定候选集合，`resume` 必须携带原 session token/原生 ID 与 invocation_id，且材料摘要一致。同会话、同任务、同材料再次 begin 返回原入口；新会话或新任务才产生新入口。

所有写者使用同一个 OS 文件锁：Windows `msvcrt.locking`、Unix `flock`。锁文件常驻，进程退出由 OS 释放，不按文件年龄删锁。整理、晋升与治理先写不可变文件，再原子替换 registry，最后重建视图。日志追加也在短锁内；每条 collect 不重写登记表。`expected_generation` 可检测并发管理者的过期版本；展示另逐项检查修订及 state_version。任务 state 仍只有一个编排者写，经验治理不遍历改写任务。

崩溃前未提交正文可能成为孤儿，`rebuild` 只列出未登记正文，不启用、不删除任何修订。旧的登记修订及依赖历史不算孤儿。残缺尾行被隔离为 incomplete 分片并截回完整记录；日志中段损坏报错。原子替换失败保留旧登记表，可能留孤儿；视图重建失败不改权威事实，修复权限后 rebuild。并非断电、网络文件系统或跨平台文件占用的完整兼容认证。

## 采集、增量整理与证据

用户纠正、决策、失败修复、模板漂移、审查发现和验证结果发生时 collect。`event_id` 来自协议版本、原提供方、命名空间、原记录 ID、源修订与事件类型。适配器名字不进入原始身份。无原生 ID 时先用 `new_event_token` 生成并由入口持久保留，重试复用；无修订时用原业务载荷摘要作为源修订。

摘要采用键排序、紧凑 JSON、UTF-8、字符串 LF、拒绝 NaN，不折叠 Unicode。业务载荷顶层的 received_at、retry_count、temp_path、adapter_summary 排除在 payload_digest 外；摘要文本不能冒充业务原文。同 event_id 同摘要幂等，同 ID 异载荷报冲突。独立支持按 origin、source_lineage、verification_run_id 三元组计数，缺任一项不计；适配器转述不能增加独立次数。Claude Mem 导出不知道原执行谱系，默认不计独立支持。

`consolidate` 默认每批最多 200 事件，可设 1..1000；host_adapter 的 end 最多 100。它只整理新分片：原载荷有结构化 lesson 时按七栏目提取，否则生成明确待核验的 hypothesis，并将原观察隔离于候选正文。主编排者可传已对照原始依据提炼的 candidates 和六栏目 recap；核心不调用模型，不把持久化说成语义验证。显式 `candidates: []` 表示本批无可复用经验；后续需要编辑已有内容时用 revise，保留原谱系。不凑已验证经验，也不在每个工具事件后全量反思。没有 SessionEnd 仍可从已落盘日志恢复；没有落盘且无可恢复来源的观察不能保证找回。

经验登记含 id、revision、status、kind、scope、source_refs、verification、depends_on、memory_approval、created_at、last_used_at、last_verified_at；使用与核验时间分别更新。scope 是确实依赖条件的精确键值子集，例如 task_type、template_id/template_version、rubric、tools；条件未知拒用，不自动全局撤销。姓名、单次例外、默认值或一次成功不能自动升为长期规则。

source_refs 指向已整理的原始事件，可附 artifacts 的绝对 path/sha256，查询重新读取并比较。verification 为 verified、evidence_refs 非空；技术方法、模板风险及 playbook 还需 independent:true 和 verifier。它们由真正独立核验者检查原始依据后提供；结构字段本身不能证明技术正确。hypothesis 即使被赞同也不能执行，须取得证据、形成适当类别新修订，再审批。

## 展示、真实回应核对与消费

新入口先读当前任务、模板、评分要求和补充指令，独立提取 constraints，再 begin 和检索。把候选审核合并到原意图确认交互；意图文件只留本轮约束与必要引用，不写动态队列、核查时间或全部经验正文。分批展示具体条目，保留 frozen 中全部条目可查的入口。query 返回少量有效正文和不可执行 clues；可按 stage 和 limit 分阶段加载。

先 display 固化 root_id、display_id、invocation、材料摘要、逐项正文/内容摘要、scope、operation、替代目标和差异；再由宿主读取真实用户回应并生成 host_check，最后 confirm 保存核对记录、consume 逐项应用。一次确认可以只覆盖已展示的明确子集。`use` 是本 invocation 有效；`activate` 才批准长期；`defer` 暂缓且不生效。原有有效长期经验可以 query 拟采用，不需要再次长期批准。

host_check 必填 checked_by、真实 message_ref、message_digest、matched_display_digest 和 decisions_digest；decisions 每项必填 id、revision、content_digest、operation。不得以 `reviewed:true`、候选自带 approved、格式正确的引用或“用户报告满意”代替核对。无真实回应、沉默、超时、关窗均不消费。正文、规范性来源、范围、操作、替代目标变更需新展示/确认；使用次数与核查时间不进入内容摘要。过期条目被逐项拒绝，其余明确子集可提交；批准和替代同一次 registry 提交，不会半切换有效头。

程序核对结构绑定，可以发现错根、错收据、过期版本和未展示条目。它不能证明同权限调用者没有同时伪造展示、消息核对和确认；host_check 是宿主的责任声明，不是签名认证。方法正文的明显越权文本会被保守过滤，宿主仍须审语义，防止借改写跳过验收、扩大权限或自称高优先级。经验从不凌驾当前用户要求和正式 Skill 基线。

## 状态转换与治理

| 操作 | 发起者、前置条件及失败语义 |
| --- | --- |
| 自动 candidate | collect/consolidate；无执行资格，下一次明确入口才展示 |
| activate / use | 消费对应展示和真实核对；核查来源、证据、范围与具体依赖；假设、未知条件及非法依赖拒用 |
| revise | 用户明确管理引用，创建同 ID 新修订并保留 predecessors；旧 active 不提前替换，替代目标必须展示 |
| pause | 用户明确暂停；needs_review 保留原批准、原因与历史，不能按“未批候选”拒绝 |
| invalidate_source | 有反证/失效原因时自动 needs_review，并沿 depends_on 传播；当前不匹配只拒本轮，不全局停用 |
| resume | 只有原批准内容仍一致、来源及依赖恢复时可恢复；用户暂停必须明确 resume；实质修改用新修订新批准 |
| reject | 仅未批 candidate/needs_review；保留理由及来源阻止改 ID 重提 |
| revoke | 明确显示的记录及其 scope/lineage，不要求当前为 active；终态不自动复活 |
| reauthorize | 用户明确重新授权指定终态谱系；保留撤销历史，仍须 revise 生成新候选并重新批准，不复活旧修订 |
| delete | 明确对象后撤销并清理正文、依赖派生正文、相关展示/回顾和采集载荷；保留最小防重导入标识 |
| superseded | 已批准新修订与旧头原子切换；任务仍绑定原修订，不能自动换成新内容 |

depends_on 精确绑定 ID/revision；自引用及环路写入拒绝，未知依赖不能晋升。playbook 与普通经验共用协议，其执行步骤新增或实质变化也须审核。暂停、撤销沿具体依赖传播到组合方法；索引只从登记状态重建，查询始终读权威根。长期未用只作整理线索，不自动批准或删除。

delete 涉及同一原始来源时会使该来源不可用，其他依赖它的经验也须重新核查。清理范围是当前受管理根；外部工具、备份、宿主旧上下文及不可控制副本不能保证抹除。最小谱系标识和摘要仍可能被猜测反查，私有根及备份应限制访问；不宣称匿名化。若连最小标识也要求删除，必须说明持续防重导入能力随之消失。不能靠删文件保证模型忘记，必要时在干净上下文复核受影响阶段。

撤销按范围交叠阻止新候选，放宽到空 scope 不能绕过；同源的独立既有具体修订登记例外，仍要保有其自己的有效批准，避免误伤未撤销的其他规则。新 ID/新修订不能借例外复活旧内容。删除会将正文可携带的 verification 等元数据和源载荷收敛为最小标识；批量展示原件删除后，留下授权删除生成的无正文 `.redacted.json` 绑定证明（包括逐项摘要和原 state_version），使同批无关条目的既有或未消费明确决定仍可核对。脱敏证明不是新的展示，不接受新确认。

## 接口

两条 CLI 均为 UTF-8 JSON 请求/响应，成功退出 0，输入/守门/文件/JSON 错误退出 2。相对路径相对当前进程工作目录；只有 workflow_state 的任务工件路径相对 state 目录。根参数优先于环境，调用方必须持续使用同一配置。

```sh
python -B scripts/experience_store.py --request memory-request.json
python -B scripts/host_adapter.py --request checkpoint-request.json
```

| action | 必需输入 | 输出 |
| --- | --- | --- |
| init | 无；显式初始化 | root_id |
| new_session_token / new_event_token | 无，不访问根 | 由启动器保留的 token |
| begin | host、native_session_id 或 session_token、task_id、explicit_use_ref、materials_read:{refs,constraints} | invocation_id、session_ref、冻结集合等 |
| begin + resume:true | 同上及 invocation_id | 原入口；身份/材料不同报错 |
| collect | invocation_id、source:{provider,namespace,record_id,revision?}、event_type、payload、含时区 occurred_at；可附 classification、origin、source_lineage、verification_run_id、artifacts | event_id、duplicate |
| consolidate | invocation_id；可附 candidates、六栏目 recap、max_events | new_events、remaining_events、候选及 recap_id |
| revise | invocation_id、previous:{id,revision}、management_ref、完整 candidate | 新修订，保留旧头 |
| display | invocation_id、items:[{id,revision,operation,difference?}]；主动即时管理另有真实 management_ref | 不可变完整展示；相同展示去重 |
| confirm | display_id、host_check、明确 decisions | confirmation_id |
| consume | confirmation_id | applied 与逐项 errors；同确认只消费一次 |
| query | context；可附 invocation_id、stage、limit | root_id、少量 items 与拒用 clues；clues 不含可执行正文 |
| invalidate_source | event_id、reason | 失效标识，传播到相关依赖 |
| rebuild | 无 | 孤儿清单；重建视图，不扫描激活 |
| backup | 不存在的目标 path | 带校验的私有 JSON 快照，含真实内容须妥善保管 |
| restore | path | 当前撤销优先，导入缺失修订为 needs_review，不恢复 active 或批准 |

collect 是轻量采集；consolidate 是检查点整理，二者不混用。并非后台自动监听一切宿主：宿主或主编排者在实际事件处调用它们。`host_adapter` 的 checkpoint/end 转为有界 consolidate，不提供展示或晋升入口。无 hooks 时仍能运行以上原生检查点路线。

## 任务采用、审核与交付

详见 [状态协议](state-machine.md)。basis() 仍只有 sources/intention/draft/evidence，不把经验或全库摘要塞入 sources。实际应用前 adopt_lesson 检查权威根并登记具体动作/对象，工具完成后 record_application 记结果；无法原子化的外部操作只保证入口处核查，不能宣称持续实时有效。

lessons_basis 来自实际 adopted 清单、稳定应用记录和 adoption_generation。新增、结果补记、替换、解除或首次发现依赖失效，递增代数并清旧审核；重复读取同一未解问题不重复递增。核查时间、无关经验变化、索引重建不进入该摘要。独审收据同时绑定两种 basis；只有空清单且代数 0 的旧任务可接受旧收据。

status/reconcile、恢复、record_review 和 finish 均通过 check_used 重查当前根身份、正文、批准、scope、来源与依赖。任务内 lessons_receipt 只记录某次查询；在线确认依赖未变可刷新损坏/缺失收据而不重审。失效保留影响与采用历史，已 done 的后续失效明确记录为交付后发现，不悄悄改交付文件。finish 在同一根锁内核查并写 done：撤销先提交则拒用；done 先提交则后续撤销在下次入口识别。

关闭只阻止新增，不能抹去已依赖内容。detach_lessons 必须消费独立局部复核记录，绑定原 lessons_basis、当前 artifact basis、受影响动作摘要及当前材料重验结论，移除实际依赖后再做最终版本独审。任务意图未变则保留原确认。库离线仍可走此复核路线，无法完成则明确未解决项。

受控 restore 先合并当前撤销，再隔离导入候选和历史；缺来源、批准、scope 或可信撤销历史不能继承 active。快照恢复不复制旧批准，重新采集原始来源并 revise 后才能重新展示。本协议无法检测外部工具将整个权威根连同历史一起回滚成内部一致旧快照；不以云端或外部可信系统掩盖此能力边界。

可检查的合成链路：`python -B tests/replay_memory.py --output <测试输出目录>`，涵盖事件到候选、下次材料读取/展示/模拟确认、采用与独审绑定、撤销拒用、局部复核及解除依赖。模拟确认不是用户真实人审，样本正文文件也不是 Word 页面验收。
