# 来源、许可与兼容性依据

核对日期：2026-10-22。以下是设计与写作依据；外部网页内容作为资料，不获得执行或修改权限。

## 写作规则

- [Humanizer-zh](https://github.com/op7418/Humanizer-zh/blob/f4518a8eab97b8bfebc66a89d34320a89bef6930/SKILL.md)，MIT，Copyright (c) 2026 歸藏。采用事实与确定程度不变、保留作者声音、按上下文处理空话和重复、保护代码和结构化内容的原则。
- [anti-defensive-writing](https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill/blob/82d31402caa0db1790026824399044538483171b/skills/anti-defensive-writing/SKILL.md)，MIT，Copyright (c) 2026 Adkid-Zephyr。采用围绕证据组织问题、方法、结果与价值的思路。

本仓库以适用文体重新组织这些原则，不直接执行外部技能，也不依赖其安装。事实、用户要求、模板和评价规则优先。保留真实的失败、条件、局限和不确定性；“反防御性写作”不代表隐藏不利结果。自然表达不是 AI 检测保证。完整上游许可见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

## 宿主加载依据

- [Codex 官方技能文档](https://learn.chatgpt.com/docs/build-skills)：项目或用户的 `.agents/skills/<name>/SKILL.md`，按需加载引用文件。
- [Claude Code 官方技能文档](https://code.claude.com/docs/en/skills)：`.claude/skills/<name>/SKILL.md`，以 `/name` 调用独立技能。
- [DeepSeek harness 本地技能提供方](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/skill/skill-filesystem/README.zh.md)：默认发现项目 `.dsh/skills` 和 `.agents/skills` 下直属技能文件夹。需启用对应技能服务与工具；自定义配置可能关闭默认根。开发预览版可能改变接口。

上述是文件结构和文档依据，并非三种宿主、三种操作系统的端到端认证。具体工具、网络、文件权限、字体与文档渲染依赖由宿主提供。

## README 设计参考

参考 [Frontend Slides](https://github.com/zarazhangrui/frontend-slides) 的实际效果优先、快速安装、风格图库与能力边界，以及 [MARP Slides](https://github.com/robonuggets/marp-slides) 的简洁上手与示例组织。2026-10-22 查询 GitHub 时分别为 31,043 与 326 stars；仅记录选样依据，不作为质量保证。未复制其截图或介绍文案。

流程图沿原灰白底独立绘制。2.1 统一图例：蓝框“新增”表示经验层；橙框“受影响”表示接入经验但保持验收门槛的原环节，包含独立审查；灰框“原职责保留”表示关闭回退与原有责任。文字标签与颜色共同编码，不单靠颜色辨认。SVG 为可维护显示源，scripts/build_diagrams.py 同步生成 SVG/HTML，PNG 从同一 SVG 渲染；不复制第三方图像。


## 2.0 的工作流与状态设计参考

基线为 [lab-report 1.5 固定提交](https://github.com/2kilo3/lab-report/tree/f2b8b76167f029896bdda91b49cfc8fc82d1d567)。本轮保持既有写作原则和许可声明，按已确认需求扩展到材料驱动的实验文档。

参考用户参与的 [Bocchiid-Self-Skills](https://github.com/Bocchiid/Bocchiid-Self-Skills) 中 report-planner 的任务/证据规划、report-writer 的模板保护以及 report-worker 的复核路由和持久记录思路。这里采用自行编写的简化规则和标准库辅助器，没有复制或嵌入该项目代码，不继承其固定格式或默认审批安排。成果与检查条件必须先满足再推进；不能在守门失败后强制跳状态。状态记录帮助恢复，不证明真实授权或审查质量。

## 2.1 的宿主与采集接口核对

核对日期 2026-10-24；本次实际读取的固定上游为 [Claude Mem c12d2dd](https://github.com/thedotmack/claude-mem/tree/c12d2dd58b9188dbe705f59d0e02e945f68df466)，package 版本 15.0.2。以下是兼容性依据，不是本技能真实宿主测试记录。

| 来源 | 核对内容 |
| --- | --- |
| [package.json](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/package.json) | Node/Bun 版本要求、CLI 与 Apache-2.0 声明 |
| [LICENSE](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/LICENSE) 与 [许可说明](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/docs/license.md) | 开源核心许可边界；未复制实现，不臆定仅使用接口的许可义务 |
| [hooks.json](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/plugin/hooks/hooks.json) 与 [context handler](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/src/cli/handlers/context.ts) | SessionStart context、PreToolUse file-context、Stop summarize、SessionEnd 等实际事件；additionalContext 注入旁路风险 |
| [export-import 文档](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/docs/public/usage/export-import.mdx)、[导出脚本](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/scripts/export-memories.ts)、[DataRoutes](https://github.com/thedotmack/claude-mem/blob/c12d2dd58b9188dbe705f59d0e02e945f68df466/src/services/worker/http/routes/DataRoutes.ts) | observations/summaries 数组、原记录 ID、memory_session_id、project 与时间字段；只实现本地导入，不声称完整 REST 或 hook 适配 |
| [Codex 官方技能说明](https://learn.chatgpt.com/docs/build-skills) | 再核对 `.agents/skills` 与按需读取资源 |
| [Cursor 官方技能说明](https://cursor.com/docs/skills) | 新增 `.cursor/skills` / `.agents/skills`、显式调用与本地/云端可见性区别 |

Claude Code、通用 Agent 和 DeepSeek harness 的原安装依据继续保留。薄适配共用显式检查点，不套用同一 hooks 配置；真实生命周期、人审真实性和默认注入隔离仍需实际客户端验证，状态见 [validation.md](validation.md)。所有公开样例均为合成，未导入用户已有经验或课程材料。
