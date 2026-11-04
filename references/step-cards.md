# Step Card：执行卡、冻结与逐步证据

Step Card（执行卡）把已确认意图翻译成**可逐步执行、可逐步验收**的原子步骤。它回答的是“具体怎么做、每步留下什么证据、本步禁止哪些捷径”，不替代 [意图清单](requirements-note.md) 回答“为什么做、交付什么、按什么标准算完成”。

> 本文件的 YAML 是**人读示例**。`scripts/workflow_state.py` 只依赖 Python 标准库，不解析 YAML；机器登记时使用同字段的 UTF-8 JSON（例如 `steps.json`），由人或工具从 YAML 转写。`[推断/扩展]` 字段命名对齐 Bocchiid `plan.json` 的 `action.kind` / `evidence.must_include`，并增加 lab-report 需要的 `modality`、`forbidden_shortcuts`、`screenshot_required`。

## 1. 与意图 MD 的关系

| 文档 | 回答 | 确认/冻结 |
| --- | --- | --- |
| 意图 MD | 要做什么、来源与理由、交付物、完成标准、内容/样式 | 用户明确确认当前版本；确认前不实施 |
| Step Card | 按什么步骤做、每步什么模态、必截点、`must_include`、`forbidden_shortcuts`、失败处理 | 卡内容经用户确认后 `frozen: true`，脚本登记 `freeze_plan` |
| Evidence Binder | 哪些真实证据文件对应哪一步、哪些 `must_include` 已逐项核对 | 全部步骤完成后 `bind_evidence`，才允许写作出口 |

- 执行卡从**已确认的意图**派生。改卡若改变任务范围、评分要求或交付物，先回到意图 MD 重新确认，不能只改卡。
- 改卡若只是执行细节（例如更好的截图位置、补充一条 `forbidden_shortcuts`），也要**重新冻结**并说明差异；不得静默换做法。
- 意图 MD 里的“复用已有环境/免做步”必须在冻结卡中显式标为 `skipped` 并写理由，不能靠模型记忆省略。脚本当前不单独解析 `skipped` 字段，仍要求该步提交能证明复用/免做依据的证据；只写“已做过”不算证据。

## 2. 字段

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `version` | 建议 | 卡格式版本，当前示例为 `"1.0"` |
| `frozen` | 是（机器登记时） | `false` 为草案；用户确认卡内容后改 `true` 再登记冻结 |
| `steps[]` | 是 | 非空步骤数组；每项是一个可验收原子动作组 |
| `id` | 是 | 卡内唯一，如 `S1`；改名会使已完成记录失配，需重新冻结 |
| `source` | 是 | 对应指导书/报告的具体章节或条目，便于追溯 |
| `goal` | 是 | 本步要完成的可判断目标 |
| `modality` | 是 | `gui` / `cli` / `mixed` / `manual`，按指导书主证据选择 |
| `tool` | 建议 | 指导书点名的具体工具/界面，如 `Postman`、`Wireshark`、`MiniEdit`；不得用同类 CLI 替代 |
| `objects` | 建议 | 本步必须出现的对象清单：拓扑节点、主机名、文件、接口或设备名；来自材料地图或指导书原文 |
| `action` | 是 | 学生视角的实际动作序列；不写“用脚本代做” |
| `screenshot_required` | 是 | 布尔值；`true` 表示本步必须有可读证据图，不能合并跳过 |
| `must_include` | `screenshot_required` 时必填 | 证据中必须可辨认的字段；逐项验收，不是泛泛“有图” |
| `forbidden_shortcuts` | 是 | 本步具体禁令，从 [禁止捷径目录](forbidden-shortcuts.md) 取模式后实例化；非空短语列表 |
| `verify` | 是 | 完成后如何判断本步真的成立 |
| `on_fail` | 是 | 失败后的有界处理，如 `retry_once → ask_user`、`replan_capture_filter` |
| `evidence_ids` | 否 | 与该步关联的证据编号，便于 Evidence Binder 和报告图号对应 |

机器登记还会检查：步骤 `id` 唯一、`modality` 合法、`screenshot_required` 为布尔、`must_include` 无重复、`forbidden_shortcuts` 非空；`gui` 步骤的 `must_include` 应写清界面/字段，不能只写“成功”。`tool` 若填写须为非空字符串；`objects` 若填写须为非空字符串数组。**脚本强制契约**：填写 `tool` 时，`must_include` 至少一项包含该工具名（如“Postman 请求与响应面板”）；填写 `objects` 时，每个对象都须出现在至少一项 `must_include` 中。缺失则 `freeze_plan` 拒绝冻结，并列出缺项。旧卡没有 `tool`/`objects` 仍可冻结。

`must_include` 写法与 `tool`/`objects` 对齐：
- 有 `tool` 时，至少一项写明该工具窗口/界面（如“Postman 请求与响应面板”），不能只写“请求成功”。
- 有 `objects` 时，逐项或成组写进 `must_include`（如“c0、s1、s2、s3、h1–h6 可见”）；不能只写“拓扑正确”。
- 指导书的附步骤/addon 要么单独成卡，要么在意图中显式写明本次不做；卡里不能静默省略。`[来源:lab8-iter]`
- 卡片不要求报告加红框/箭头。标注默认关闭（opt-in）；用户明确要求时才在证据展示副本上加，且不得遮挡 `must_include` 字段。软件自带的红虚线路由/选中高亮不算报告标注。`[来源:lab8-iter]`

## 3. 冻结流程

1. **起草**：按已确认意图写 `steps`（人读 YAML + 机器 JSON 同字段），此时 `frozen: false`。
2. **给用户看**：与意图确认或执行方案一起展示；用户确认卡内容和步骤边界。
3. **标记并冻结**：把卡改为 `frozen: true`，调用 `freeze_plan`，请求中带卡路径和真实确认引用 `message_ref`。脚本校验卡结构，并记录卡摘要与当前意图摘要。
4. **执行**：一次做一步；每步后观察结果，调用 `complete_step`，提交真实证据路径和逐项 `must_include` 结果。
5. **封存**：全部步骤完成后调用 `bind_evidence`。脚本核对所有步骤、证据文件和摘要，生成 `evidence_binder`。
6. **写作出口**：`submit_draft` 在 `execution_required=true`（新任务默认）或登记过执行卡时，要求冻结卡 + 全部步骤完成 + 证据绑定通过；纯审查、纯写作须在确认意图前用 `set_execution_required` 显式关闭，旧状态缺该字段时保留 deprecated 旁路。

卡与意图摘要绑定：意图 MD 变化会使旧卡失效并要求重新确认与冻结，不能沿用旧步骤记录。**改卡/重冻结**：修改卡文件后再次调用 `freeze_plan`，必须提供 `reason`；脚本清除旧的步骤完成记录和证据绑定，要求重新执行受影响步骤。发现更优解、指导书歧义或环境变化时，先改卡再继续，不先做后补。

**证据重采**：如果证据文件在完成步骤后被替换或删除，`status` 会发现摘要不符/文件缺失，使相应步骤和证据绑定失效；重新采集后重新 `complete_step`。不要手改状态 JSON 绕过。

## 4. 脚本闸门（摘要）

| 动作 | 前置 | 拒绝条件 |
| --- | --- | --- |
| `freeze_plan` | 意图已确认，phase=`produce` | 卡未标 `frozen: true`；缺 `message_ref`；步骤结构非法；`tool`/`objects` 未被 `must_include` 点名覆盖；重冻结缺 `reason`；意图已变化 |
| `complete_step` | 已冻结执行卡，phase=`produce` | 执行卡未冻结；步骤不存在或已完成；证据文件缺失/为空；`screenshot_required` 步骤无图片证据；`must_include` 未逐项标 `pass` |
| `bind_evidence` | 所有步骤已完成 | 仍有未完成步骤；证据缺失/摘要不符 |
| `submit_draft` | 登记过执行卡时 | 未冻结；步骤未全完成；证据绑定缺失或与当前卡/步骤不符 |

脚本只检查文件存在、摘要和结构化结果，不能判断截图内容是否真的可读、操作是否真的发生；这些仍由执行者和独立审查负责。

## 5. 示例（5 张）

以下示例覆盖下载、配置编辑、抓包、编译运行、进程检查。实际任务按指导书裁剪，不照抄字段值。

```yaml
# steps.yaml（建议同时生成 实验执行卡.md 人读版）
version: "1.0"
frozen: false  # 用户确认后 true
steps:
  - id: S1
    source: "指导书§3.1 从课程网站下载实验包"
    goal: "完成实验包下载并在文件夹中可见"
    modality: gui   # gui | cli | mixed | manual
    action: "打开课程下载页 → 点击下载 → 在资源管理器打开目标目录"
    screenshot_required: true
    must_include:
      - "浏览器下载页或下载进度/完成提示"
      - "资源管理器中可见实验包文件名与大小"
    forbidden_shortcuts:
      - "curl/wget/Invoke-WebRequest 静默下载作为本步主证据"
      - "SHA-256/Get-FileHash/md5 画面作为本步主证据"
      - "仅 ls/dir 文本输出冒充文件夹查看"
    verify: "目录截图可辨认文件名；不得声称字节完整除非另有步骤"
    on_fail: "retry_once → ask_user"
    evidence_ids: ["E1"]

  - id: S2
    source: "指导书§3.2 用记事本打开 config.ini 修改 server=..."
    goal: "在 GUI 编辑器中修改并保存配置"
    modality: gui
    action: "记事本打开 config.ini → 修改 → 保存"
    screenshot_required: true
    must_include:
      - "编辑器标题栏含文件名"
      - "修改后的 server= 行可读"
      - "保存后文件仍打开或保存成功提示"
    forbidden_shortcuts:
      - "sed/echo重定向/Set-Content 静默改文件只交 diff"
      - "cat 终端输出冒充记事本"
    verify: "重新打开或同屏可见新值"
    on_fail: "restore_backup → retry"
    evidence_ids: ["E2"]

  - id: S3
    source: "指导书§4 使用 Wireshark 捕获并查看 Packet-In"
    goal: "GUI 中选中报文并展开字段"
    modality: gui
    tool: "Wireshark"
    action: "启动 Wireshark → 开始捕获 → 选中 Packet-In → 展开报文树"
    screenshot_required: true
    must_include:
      - "Wireshark 主窗口"
      - "选中 Packet-In"
      - "报文树中 Version/Type/Length 等关键字段可读"
    forbidden_shortcuts:
      - "tshark/tcpdump 文本冒充 Wireshark"
      - "只提供 pcap 路径无界面截图"
      - "合并「开始捕获」与「展开字段」导致缺选中态"
    verify: "字段名与指导书一致且可读"
    on_fail: "replan_capture_filter"
    evidence_ids: ["E3"]

  - id: S4
    source: "指导书§5 编译 hello.c 并运行"
    goal: "分步展示编译与运行输出"
    modality: cli
    action: "在可见终端执行编译命令；再执行运行命令"
    screenshot_required: true
    # 若指导书拆成两步，应拆成 S4a/S4b；此处演示「一步内仍禁止只留最后一屏」
    must_include:
      - "编译命令与退出状态/无错误输出"
      - "运行命令与程序输出"
      - "提示符"
    forbidden_shortcuts:
      - "编译与运行合并到只截最终输出一屏（当指导书分列时）"
      - "未执行却写编译通过"
      - "伪造终端文本图"
    verify: "两段命令均可见；后台定位工具不替代本屏"
    on_fail: "fix_code → rebuild"
    evidence_ids: ["E4a", "E4b"]

  - id: S5
    source: "指导书§2 在任务管理器中确认服务已启动"
    goal: "GUI 确认进程/服务状态"
    modality: gui
    action: "打开任务管理器或服务管理 → 定位目标进程/服务"
    screenshot_required: true
    must_include:
      - "任务管理器/服务窗口标题"
      - "目标进程或服务名称与状态"
    forbidden_shortcuts:
      - "tasklist/Get-Process/ps 文本冒充任务管理器"
      - "假设服务已启动而跳过本步"
    verify: "状态与指导书期望一致"
    on_fail: "start_service_via_guide_steps → recapture"
    evidence_ids: ["E5"]
```

机器登记用的 JSON 与上面同字段，例如：

```json
{
  "version": "1.0",
  "frozen": true,
  "steps": [
    {
      "id": "S1",
      "source": "指导书§3.1 从课程网站下载实验包",
      "goal": "完成实验包下载并在文件夹中可见",
      "modality": "gui",
      "action": "打开课程下载页 → 点击下载 → 在资源管理器打开目标目录",
      "screenshot_required": true,
      "must_include": ["浏览器下载页或下载进度/完成提示", "资源管理器中可见实验包文件名与大小"],
      "forbidden_shortcuts": ["curl/wget/Invoke-WebRequest 静默下载作为本步主证据", "SHA-256/Get-FileHash/md5 画面作为本步主证据", "仅 ls/dir 文本输出冒充文件夹查看"],
      "verify": "目录截图可辨认文件名；不得声称字节完整除非另有步骤",
      "on_fail": "retry_once → ask_user",
      "evidence_ids": ["E1"]
    }
  ]
}
```

具名工具与对象清单的最小写法（`[来源:lab8-iter]`）：

```yaml
  - id: S6
    source: "指导书§4.2 用 Postman 验证 REST 服务"
    goal: "在 Postman 中发起 GET 并读响应"
    modality: gui
    tool: "Postman"
    objects: ["http://<客户机IP>:5000/restconf/data/..."]
    action: "在 Postman 填 URL → Send → 展开响应"
    screenshot_required: true
    must_include:
      - "Postman 窗口与请求 URL"
      - "响应状态码与响应体关键字段"
    forbidden_shortcuts:
      - "curl/Invoke-RestMethod 输出冒充 Postman 窗口"
      - "只交接口返回值文本，不交 Postman 界面"

  - id: S7
    source: "指导书§2 基础拓扑"
    goal: "按 c0+s1/s2/s3+h1–h6 建成拓扑"
    modality: gui
    tool: "MiniEdit"
    objects: ["c0", "s1", "s2", "s3", "h1", "h2", "h3", "h4", "h5", "h6"]
    action: "在 MiniEdit 放置节点并连线"
    screenshot_required: true
    must_include:
      - "MiniEdit 画布中 c0、s1/s2/s3、h1–h6 全部可见"
      - "节点名称与连线可读"
    forbidden_shortcuts:
      - "用同实验的进阶 1s3h 拓扑冒充基础拓扑"
      - "只交 ping 输出不交拓扑画布"
```

## 6. 反例（不要把卡写成这样）

- `must_include: ["截图"]`：没有可核对字段，等于没验收。
- `forbidden_shortcuts: ["不要作弊"]`：不是可粘贴的具体短语，无法指导执行。
- 把“下载 + 安装 + 启动”写成一步，且只要求一张最终界面：会漏掉指导书要求的中间验收点。
- `modality: gui` 但 `must_include` 只写“成功”：无法排除 CLI 文本冒充或空白截图。
- 先执行后补卡：违反“执行前冻结”，`complete_step` 会因无冻结卡拒绝。
