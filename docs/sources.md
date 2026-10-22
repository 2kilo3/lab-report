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

流程图按 diagram-design 的默认灰白与橙色设计规则独立绘制；示例与截图的来源在 README 中分别注明。

