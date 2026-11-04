# 禁止捷径目录（按类别）

本目录按**类别 + 模式**组织，不是穷举命令清单。同一个模式可能有很多等价命令；换成另一个工具名不改变性质。**Step Card 必须实例化 `forbidden_shortcuts`**：把本步真正要防的具体短语写进卡里，而不是只写“要像人一样操作”。执行阶段先读 [仿人操作与证据保真](human-ops.md)，再按本目录给执行卡补禁令。

每项包含：Pattern（中英模式名）、Why AI prefers（模型为何爱用）、Human alternative（学生常见做法）、Allowed when（仅当指导书/意图明确要求时才允许作为主证据）、Step Card 写法（`modality` + `forbidden_shortcuts` 示例）。

来源标记同 [human-ops.md](human-ops.md)：`[来源:lab-report]`、`[来源:Bocchiid]`、`[来源:Anthropic-CU]` 表示对应仓库/文档有原文或同义表述；`[推断/扩展]` 表示由同一原则推广，旧版仓库未逐字写出。

## B1. Download / install / verify integrity（下载·安装·完整性）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B1.1 | **Hash-as-download-proof** / 哈希画面当下载过程 `[来源:lab-report]` | 一条 `sha256sum`/`Get-FileHash` 同时“证明”存在+完整 | 浏览器/实验页点下载 → 打开文件夹看文件名与大小；需要完整时再后台哈希 | 指导书明确要求“计算并截图校验和/哈希” | `modality: gui`（或 mixed）；`forbidden_shortcuts: ["用 SHA-256/Get-FileHash/md5 画面作为本步主证据", "跳过下载按钮直接断言文件已在"]` |
| B1.2 | **Silent curl/wget drop** / 静默拉取冒充页面下载 `[推断/扩展]` | `curl -O` 最快、可脚本 | 按指导书从指定页面/链接点击下载 | 指导书写明用 curl/wget/aria2 | `forbidden_shortcuts: ["curl/wget 静默下载替代页面点击", "只交 ls 输出不交下载对话框/文件夹"]` |
| B1.3 | **Package-manager skip UI** / 包管理器跳过安装向导 `[推断/扩展]` | `apt/choco/winget` 一行装完 | 指导书的安装程序/向导逐步点“下一步”并截关键页 | 指导书明确 CLI 安装 | `modality: gui`；禁“silent install / /S /quiet 跳过向导截图” |
| B1.4 | **Existence⇒integrity** / 见文件就声称完整 `[来源:lab-report]` | 偷换“存在”为“字节一致” | 分开写：存在 / 可打开 /（若要求）校验 | 从不允许混为一谈 | `must_include` 分写结论；禁“见文件即宣称哈希一致” |

## B2. File open / view / edit（打开·查看·编辑）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B2.1 | **cat/Get-Content as code view** / 终端摘行冒充看代码 `[来源:lab-report]` | 终端最快 | 编辑器/IDE/记事本打开真实文件并定位 | 指导书只要终端 `type`/`cat` 展示 | `modality: gui`；`forbidden_shortcuts: ["cat/type/Get-Content/sed -n 画面替代编辑器打开"]` |
| B2.2 | **head/tail fragment as full proof** / 片段冒充全文 `[推断/扩展]` | 少 token | 按报告要求展示完整关键段；长代码连续分屏各有图题 `[来源:lab-report]` | 指导书只要某几行 | `must_include: ["文件名或路径可见", "关键行可读"]` |
| B2.3 | **Synthetic editor chrome** / 伪造编辑器图 `[来源:lab-report]` | 生成图省事 | 真实打开再截 | **永不**作为实验证据 | 绝对禁止；独审拒绝 |

## B3. Network capture（抓包）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B3.1 | **tshark/tcpdump as Wireshark GUI** / CLI 抓包冒充 Wireshark `[推断/扩展]`；Bocchiid 执行卡示例强调 Wireshark 报文树字段 `[来源:Bocchiid]` | CLI 易自动化 | 打开 Wireshark（或指导书指定 GUI），选中报文、展开树，截 Version/Type 等字段 | 指导书明确 tshark/tcpdump | `modality: gui`；`forbidden_shortcuts: ["tshark/tcpdump 文本输出冒充 Wireshark 界面", "只交 pcap 路径不交报文树截图"]`；`must_include` 写清字段名 |

## B4. Process / service check（进程·服务）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B4.1 | **tasklist/ps as Task Manager** / CLI 冒充任务管理器 `[推断/扩展]` | CLI 一行 | 任务管理器/活动监视器/服务 MMC 等指导书面板 | 指导书写 `ps`/`systemctl status` | `modality: gui`；禁“tasklist/Get-Process 冒充任务管理器截图” |
| B4.2 | **service status text only when UI required** / 只交服务状态文本 `[推断/扩展]` | `systemctl` 快 | 服务管理 GUI 或实验软件自带状态页 | CLI 写在指导书里 | 同上 |

## B5. Config edit（改配置）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B5.1 | **sed/echo-redirect as Notepad/IDE** / 脚本改配置冒充编辑器 `[推断/扩展]`；Bocchiid `file_edit` 要求备份+改指定行 `[来源:Bocchiid]` | 脚本改文件 | 记事本/IDE/设备 Web UI 打开、修改、保存；需要时截保存前后 | 指导书明确 sed/ansible/脚本下发 | `modality: gui` 或 `file_edit` 且展示方式跟指导书；`forbidden_shortcuts: ["sed/echo>/Set-Content 静默改完只交 diff 冒充 GUI 编辑"]` |
| B5.2 | **Skip save dialog / skip apply button** / 跳过保存或应用确认 `[推断/扩展]` | 直接写盘 | 点保存/应用/提交，截对话框或成功提示 | 无 GUI 的纯文件实验 | `screenshot_required` 含保存/应用确认帧 |

## B6. Compile / run（编译·运行）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B6.1 | **One-shot batch vs step-by-step** / 合并编译运行 `[推断/扩展]` | `make && ./a.out` 合并 | 指导书分“编译”“运行”“查看输出”则分步截 | 指导书本身就是一条命令 | 每步独立 `screenshot_required`；禁“合并编译运行只留最后一屏” |
| B6.2 | **Claim pass without visible run** / 未运行却写通过 `[来源:lab-report scenarios]` | 文案假装跑过 | 可见终端：命令+关键输出+提示符 `[来源:Bocchiid automation]` | — | 禁“未运行写测试通过”；`must_include: ["命令行", "输出", "提示符"]` |

注：`[来源:lab-report]` 明确**正常终端编译、运行、`ping` 不受禁**——禁的是**展示方式造假**，不是禁终端。`[推断/扩展]` 把同一区分推广到其它 CLI 实验步骤。

## B7. Screenshots（截图本身）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B7.1 | **Skip intermediate dialogs** / 跳过中间对话框 `[推断/扩展]` + 用户痛点 | 少几张图 | 下载中/安装下一步/UAC/登录框等卡上要求的中间态都要 | 卡未要求该中间态 | 中间验收点各有 `screenshot_required` |
| B7.2 | **CLI text as GUI proof** / CLI 文本冒充 GUI `[来源:Bocchiid]` | 替换模态 | GUI 步必须 GUI 图 | — | 硬拒绝 |
| B7.3 | **Composite / fake / stock / generative** / 拼图、网图、生成图 `[来源:lab-report]` `[来源:Bocchiid]` | 省事、好看 | 真实窗口采集；可裁剪+少量框线，不改结果 | **永不** | 禁 P 图、网图冒充、生成编辑器/终端图 |
| B7.4 | **Blank/loading as success** / 空白或加载中当成功 `[来源:lab-report scenarios]` | 匆忙往下走 | 区分“未知”与“失败”；补采可读图 | — | 空白图不得 `complete_step` |
| B7.5 | **Filename/order as identity** / 用文件名或排序当身份 `[来源:lab-report]` | 懒得看图 | 按图片内容核实再插入 | — | Evidence Binder 按内容绑定 |
| B7.6 | **Over-capture every click** / 截每个点击 `[来源:lab-report]` 现有规则 | — | 不截每个滚动/点击；但**不能**用本条合并掉卡上的必截点 | — | 已改写为：截卡规定的必截点，不截无意义点击，不合并中间验收点 |

## B8. Privilege / admin（权限·提权）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B8.1 | **Auto-elevate / skip UAC** / 静默提权跳过 UAC `[推断/扩展]` | 无交互 | 学生可见的 UAC/授权对话框要点“是”并截（若指导书展示提权） | 无 GUI 的服务器实验且指导书无 UAC | `forbidden_shortcuts: ["静默提权跳过 UAC 截图"]` |
| B8.2 | **sudo without showing prompt when guide shows it** / 指导书要求时隐藏 sudo 提示 `[推断/扩展]` | 已缓存凭证 | 展示密码/确认提示（注意脱敏） | 指导书不要求展示 | 脱敏规则见 [执行与取证](execution.md) |

## B9. VM / remote（虚拟机·远程）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B9.1 | **Headless shortcut** / 无头模式代替图形控制台 `[推断/扩展]` | API/ssh 最快 | VirtualBox/VMware/Hyper-V 窗口或指导书要求的控制台 | 指导书明确 headless/SSH-only | `modality: gui`；禁“仅 SSH 输出冒充 VM 窗口操作” |
| B9.2 | **Wrong environment attribution** / 混用环境证据 `[来源:lab-report]` | 混用宿主机证据 | 标明宿主机 vs VM vs 容器；截图含可辨认环境线索 | — | `must_include` 含环境可辨认信息 |

## B10. Package / env bootstrap（环境准备）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B10.1 | **One-liner vs multi-step UI** / 一行装依赖代替逐步安装 `[推断/扩展]`；Bocchiid 不擅自装系统包 `[来源:Bocchiid]` | 一行装依赖 | 按实验指导逐步装、逐步截 | 指导书给出精确命令且只要终端证据 | 分步卡；禁“合并安装向导” |
| B10.2 | **Global install / setx / profile** / 全局安装或改 profile `[来源:Bocchiid]` | 一劳永逸 | 任务 venv / 临时 env；先问用户 | 用户明确授权全局 | 禁全局 pip/setx/改 profile（安全+仿人） |

## B11. Evidence substitution（证据置换）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B11.1 | **Result-only without process** / 只留终态无过程 `[来源:Bocchiid evidence-planning]` | 只留终态 | 操作前基线 + 操作中关键配置 + 操作后验证 | 评分只看结果且意图确认可跳过程（罕见） | 阶段组 L1 覆盖过程 |
| B11.2 | **Log file instead of required UI** / 日志代替指定界面 `[推断/扩展]` | 易采集 | 指导书指定界面 | 指导书接受日志 | modality 对齐 |
| B11.3 | **Old evidence as current** / 旧证据当本轮 `[来源:lab-report scenarios]` | 复用省事 | 环境/配置变了重采 | 证明“未变化”且仍有效 | 禁改日期伪装本轮 |

## B12. Step merging / skipping acceptance points（并步·跳验收）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B12.1 | **Merge steps to save shots** / 合并步骤少截图（用户痛点） | 少步少图 | 一卡一步（或卡内声明的原子动作组） | 用户确认改卡合并 | 未改卡禁止合并；`on_fail: replan` |
| B12.2 | **Skip“详细/完整”过程** / 省略过程证据 `[来源:Bocchiid]` 评分词→证据 | 赶工 | 过程证据覆盖关键步骤 | — | Evidence Binder 拒写作 |
| B12.3 | **Batch actions without verify** / 不验证就批量操作 `[来源:Anthropic-CU]` | 一批点完 | 依赖视觉结果的动作不要 batch；每组结束截图 | 子动作互不依赖视觉 | Operator：观察→动作→截图→gate |

## B13. “Already done” assumptions（已做过假设）

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B13.1 | **Assume pre-installed / pre-configured** / 假设已经装好配好 `[推断/扩展]` | 跳过准备步 | 按指导书再走一遍准备并截，或证明复用经用户确认 | 意图 MD 写明“复用已有环境”且列出免做步 | 免做步必须在冻结卡里显式 `skipped` + 理由 |
| B13.2 | **Assume action succeeded without screenshot** / 无图假设成功 `[来源:Anthropic-CU]` | 省一轮 | 每步后评估截图一句话 | — | gate 无图拒 `complete_step` |

## B14. Tool-name substitution（具名工具不可替换）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B14.1 | **Postman-vs-curl** / 用 CLI 冒充具名 GUI 工具 | `curl` 一条命令即可拿到响应，省去开窗口和排版 | 按指导书在 Postman（或其它点名工具）中建请求、发送、截请求与响应面板 | 指导书明确要求用 curl/Invoke-RestMethod | `modality: gui`；`tool: "Postman"`；`must_include: ["Postman 窗口", "请求 URL", "响应状态码/关键字段"]`；禁“curl/Invoke-RestMethod 输出冒充 Postman 窗口” |
| B14.2 | **Hidden host→guest forwarding** / 不说明转发关系 | 宿主机 Postman 能通客户机服务，正文省略中间转发 | 正文如实写“宿主机 Postman 经本地端口转发访问客户机 REST”；证据仍截 Postman 窗口 | — | `tool` 写 Postman；`forbidden_shortcuts: ["只交 curl 返回值，不交 Postman 界面", "省略端口转发说明"]` |

判断口径：指导书写了什么具名工具，主证据就是什么；同族 CLI 只能后台自检，不能改写成学生操作步骤。

## B15. Object-set substitution（对象清单不可替换）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B15.1 | **Wrong topology** / 用另一拓扑冒充基础拓扑 | 进阶拓扑已建好，截图更“完整” | 按指导书重建/打开基础拓扑，节点集合与连线逐项可见 | 指导书明确允许复用且对象集合相同 | `objects: ["c0","s1","s2","s3","h1"…"h6"]`；`must_include` 逐项写节点名；禁“用进阶 1s3h 拓扑冒充基础拓扑” |
| B15.2 | **Partial object list** / 只截部分对象就称完成 | 少截少核对 | 全部指定节点/主机名/文件在同一或连续可读证据中出现 | 指导书只要求子集 | `objects` 与 `must_include` 一一对应；禁“只截 c0+s1 就称 c0+s1/s2/s3+h1–h6 已建” |

## B16. Prompt / batching imitation（提示符与批量合成）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B16.1 | **Foreign prompt** / 非约定提示符冒充学生终端 | 通用 root shell 最省事 | 使用指导书环境的真实提示符（如 `ubuntu@sdnhubvm…$`），保留用户名/主机线索 | 指导书明确使用该 shell/提示符 | `must_include` 含“提示符与环境可辨认”；禁“`bash-4.3$`/`root@localhost` 等非约定提示符冒充” |
| B16.2 | **One-line batch for multi-step guide** / 分号批量合成一屏 | 一条命令跑完所有步骤 | 指导书分几步就分几次真实执行与截取；保留每步输出 | 指导书本身就是一条命令 | 每步独立 `screenshot_required`；禁“用 `;`/`&&` 把多步合成一屏后只截最终输出” |

## B17. Annotation defaults（报告标注）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B17.1 | **Auto red-box everything** / 默认满图红框 | 看起来“重点突出” | 默认不画；用户明确要求时才加少量标注 | 用户明确要求标注 | 卡片不要求标注；`forbidden_shortcuts: ["默认加红框/箭头"]` |
| B17.2 | **Occluding or skewed boxes** / 标注遮挡或歪斜 | 随手画框覆盖字段 | 只框关键区域，不遮 `must_include` 字段，框线与内容大致轴对齐 | 用户要求标注 | 独审核对关键字段未被遮挡；禁“红框盖住状态码/节点名” |

说明：MiniEdit 控制链路等软件自带红虚线、选中高亮不算“报告标注红框”，不能据此判违规，也不能拿它冒充用户要求的标注。

## B18. Cross-round evidence（跨轮证据）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B18.1 | **Stale MAC/annotation as current** / 旧会话图冒充本轮 | 旧图现成 | 配置、MAC、拓扑或会话轮次变化后重采；旧标注一并重做 | 证明对象与本轮完全相同且仍有效 | `must_include` 含本轮可辨认的 MAC/主机名/轮次线索；禁“旧图带过时标注或旧 MAC 直接复用” |

## B19. Style escalation（样式升级）`[来源:lab8-iter]`

| # | Pattern | Why AI prefers | Human alternative | Allowed when | Step Card |
| --- | --- | --- | --- | --- | --- |
| B19.1 | **Heading black-font blow-up** / 小节标题换黑体放大 | “标题要醒目” | 与正文同中文字体、同字号；模板允许时仅加粗 | 模板明确规定该级标题字体/字号 | 非执行卡项，由 [文档输出](document-output.md) 与 [审查清单](review-checklist.md) 核对；禁“把「1. 进阶 A…」改为黑体大字” |

## 使用提醒

- 本目录只提供**类别与模式**；落地时把与本步相关的 2–4 条具体禁令抄进 Step Card 的 `forbidden_shortcuts`，并让 `must_include` 写出可核对的证据字段。
- 同一模式在不同实验里可能有不同边界；是否允许以**指导书原文/已确认意图**为准，不以工具是否方便为准。
- 终端本身不是捷径。可见终端中的编译、运行、`ping` 按指导书照常使用；被禁止的是用终端文本冒充 GUI 过程，或伪造未发生的运行。
- 具名工具、对象清单、提示符、标注和跨轮证据按 B14–B18 检查；报告样式升级按 B19 检查。指导书附步骤/addon 未进意图也未显式不做，按漏项处理，不当作“可选优化”。
- 生成图、网图、P 图、伪造编辑器/终端 chrome 没有“允许”分支；独立审查应直接拒绝。
