# 宿主与可选采集来源

核对日期 2026-10-24。所有路线共用 [经验协议](memory.md)；本仓库不注册全局 hooks，不自动安装插件、不上传材料。可运行的薄适配器为 `scripts/host_adapter.py`，只处理显式 begin、collect、checkpoint/end 与本地 Claude Mem 导出。

| 宿主 | 保留/新增说明 | 当前可执行路线 | 验证层级 |
| --- | --- | --- | --- |
| Claude Code | 保留 `.claude/skills/lab-report` | 原生检查点，无 Claude Mem 也可用；可选离线导出输入 | 核对官方插件源码/导出格式，合成离线测试；未真实客户端运行 |
| Codex | 保留 `.agents/skills/lab-report` | 宿主传原生会话 ID，或显式 token | 核对官方技能文档；CLI 在 Windows 实测，未原生生命周期端到端测试 |
| Cursor | 新增 `.cursor/skills/lab-report` 说明；也支持 `.agents/skills` | 相同显式检查点，不套用 Claude hooks | 核对官方技能目录说明；未真实客户端运行 |
| 通用 Agent | 保留显式读取 SKILL.md | 启动器保留 token，无 hooks 用阶段检查点 | 合成核心测试，不承诺原生自动监听 |
| DeepSeek harness | 保留 `.dsh/skills` 与原有提供方约束 | 相同阶段检查点 | 保留原固定源码依据，未新增原生 hooks 承诺或客户端测试 |

## Claude Mem 核对结果

对象是 [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)，不是 claude-code-memory。实际可访问 main 为 `c12d2dd58b9188dbe705f59d0e02e945f68df466`，package.json 版本 15.0.2，声明 Node >=20.12.0、Bun >=1.1.31。核心协议不依赖这些运行时；只有用户自行选择运行上游时才涉及其数据库、worker、模型或其他依赖。核对上游 LICENSE、docs/license.md 和 package.json 的开源核心声明为 Apache-2.0；未复制实现，也不把仅调用格式解释为必须重许可。

该提交 plugin/hooks/hooks.json 含 Setup、SessionStart、UserPromptSubmit、PostToolUse、PostToolUseFailure、PreToolUse、Stop 和 SessionEnd。SessionStart 的 context 与 PreToolUse 的 file-context 可产生模型上下文；context.ts 明确返回 additionalContext。Stop 是 summarize，SessionEnd 是 session-end，不能把两者都理解为“用户开始新技能审核”。不将这些上游 hooks 复制成其他宿主配置。

官方 export-import 文档描述 observations、sessions、summaries、prompts 的 JSON 导出；实际导出脚本使用原始记录并保存这些数组。适配器只读取已授权导出中的 observations/summaries，不读取会话全文或 prompts，不连接默认端口，不访问数据库。每条要求 id、memory_session_id、project、created_at，按明确 project 筛选；source_namespace 应为稳定原安装标识，不能随重导出改变。原 id 与内容摘要修订进入统一 event 身份，观察及摘要均先作 inference/hypothesis，不继承上游 importance、approved 或成功总结。字段与谱系未知时不计算独立支持次数。

请求示例（全部为合成占位，实际使用替换真实引用）：

```json
{
  "action": "claude_mem_export",
  "path": "authorized-private-export.json",
  "invocation_id": "原 begin 返回的 invocation_id",
  "source_namespace": "稳定原安装标识",
  "project": "当前已授权项目名",
  "isolation": {
    "mode": "clean_context",
    "verified_by": "实际宿主编排者",
    "evidence_ref": "实际核对插件禁用及干净上下文的记录"
  }
}
```

用 `python -B scripts/host_adapter.py --request request.json` 导入，再 checkpoint。隔离字段只检查宿主责任声明的结构，不能证明运行时真的隔离。本次没有真实 Claude Mem/Claude Code 环境，未技术验证所有自动注入通道可按项目安全隔离，因此默认不启用在线集成；交付的是离线格式归一化器。实际使用前，宿主必须核对其当前版本及真正干净的执行上下文。停用本适配器不能停掉上游全局注入；已有上下文中的内容也不能靠删除文件保证遗忘。

云端/本地配置、权限、超时和信任分别处理。适配器 end 只处理最多 100 个新增事件，不展示、不消费批准，不执行长反思；remaining_events 留给后续显式检查点。重试保留来源 ID/修订，外部旧观测不能绕过当前拒绝或撤销范围。完整固定源码链接见 [来源说明](../docs/sources.md)。
