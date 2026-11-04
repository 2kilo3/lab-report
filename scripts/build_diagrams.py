#!/usr/bin/env python3
"""Maintain the two static SVG/HTML sources. PNGs are rendered from these SVGs."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'docs' / 'images'
PAPER, INK, SOFT = '#f5f5f5', '#2d3142', '#4f5d75'
COLORS = {'new': '#2563a6', 'affected': '#bf4520', 'original': '#697386'}


def text(x, y, label, size=16, color=INK, weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(label)}</text>'


def box(x, y, width, height, label, lines, kind, tag=None):
    color = COLORS[kind]
    tag = tag or {'new': '新增', 'affected': '受影响 · 原门槛保留', 'original': '原职责保留'}[kind]
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="{PAPER}" stroke="{color}" stroke-width="2"/>'
            + text(x + 16, y + 26, tag, 13, color)
            + text(x + 16, y + 60, label, 22, INK, 600)
            + ''.join(text(x + 16, y + 88 + 24 * i, line, 15, SOFT) for i, line in enumerate(lines)))


def arrow(path, dashed=False):
    return f'<path d="{path}" fill="none" stroke="{SOFT}" stroke-width="2" marker-end="url(#arrow)"' + (' stroke-dasharray="5 4"' if dashed else '') + '/>'


def save(name, title, desc, height, content, legend_new='新增：经验层'):
    legend = ''.join(f'<rect x="{40 + i * 320}" y="{height - 46}" width="20" height="20" fill="none" stroke="{color}" stroke-width="2"/>'
                     + text(72 + i * 320, height - 30, label, 15, SOFT)
                     for i, (color, label) in enumerate([(COLORS['new'], legend_new), (COLORS['affected'], '受影响：原环节与门槛保留'), (COLORS['original'], '灰框：保持原职责')]))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 {height}" role="img" aria-labelledby="{name}-title {name}-desc">'
           f'<title id="{name}-title">{escape(title)}</title><desc id="{name}-desc">{escape(desc)}</desc>'
           '<defs><style>text{font-family:"Microsoft YaHei","Noto Sans SC",sans-serif}</style>'
           f'<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="{SOFT}"/></marker></defs>'
           f'<rect width="1200" height="{height}" fill="{PAPER}"/>'
           + text(40, 44, 'LAB-REPORT / 2.2', 14, SOFT) + text(40, 88, title, 30, INK, 600)
           + content + f'<path d="M40 {height - 64} H1160" stroke="#bfc0c0"/>' + legend + '</svg>')
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / (name + '.svg')).write_text(svg + '\n', encoding='utf-8')
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title><style>body{{margin:0;padding:24px;background:{PAPER}}}.diagram-container{{overflow-x:auto}}'
            'svg{display:block;width:100%;min-width:1200px}@media print{svg{min-width:0}}</style><body><div class="diagram-container">'
            + svg + '</div></body></html>\n')
    (ROOT / (name + '.html')).write_text(html, encoding='utf-8')


def build():
    stages = [('01 意图与确认', ['地图条目 → 意图清单', '合并经验审核后确认']), ('02 实验与取证', ['冻结 Step Card', '逐步取证与绑定']),
              ('03 写作与排版', ['副本允许区域', '保护固定区与样式']), ('04 独立审查', ['白名单投喂与 REVIEW 表', '双重版本绑定']),
              ('05 复核与交付', ['最后页面与作者回读', 'finish 当前撤销核查'])]
    flow = arrow('M140 236 V268')
    flow += ''.join(arrow(f'M{x + 200} 342 H{x + 228}') for x in (40, 272, 504, 736))
    flow += arrow('M600 416 V452')
    flow += arrow('M600 572 V608', True)
    flow += arrow('M600 728 V764', True)
    flow += box(40, 116, 1120, 120, '00 材料地图 · 意图前的硬门', ['通读全部材料 → 索引式 MATERIALS_MAP；每条硬要求引用 map_id', '关键材料分 subagent / 新 session 精读；地图只记定位与短引文'], 'new', '新增 · 2.2 硬门')
    for i, (label, lines) in enumerate(stages):
        flow += box(40 + i * 232, 268, 200, 148, label, lines, 'affected')
    flow += box(40, 452, 1120, 120, '分段 session / subagent 编排', ['材料 → 意图 → 执行 → 写作 → 独审 → 修订；只共享短交接包', '一个编排者写 state.json；共享 VM 同时只有一个执行者；只切上下文，不切权限'], 'new')
    flow += box(310, 608, 580, 120, '本轮增量采集 → 检查点保存候选', ['结尾只落盘；下次明确使用再读材料、展示、人审'], 'new')
    flow += box(40, 764, 1120, 120, '关闭 / 空库 / 不可用时的原流程', ['从未采用：正常继续；已经采用：保留依赖，恢复核查或局部复核后显式解除'], 'original')
    flow += text(40, 912, '统一核查位置：应用前、status / 恢复、record_review、finish；撤销不直接改写任务状态。', 16, SOFT)
    save('workflow', '实验文档 · 材料地图、五段流程与受监督经验', '顶部蓝框为 2.2 材料地图硬门，橙框为受影响的五段流程，蓝框为新增编排与经验采集，灰框为原流程回退；验收门槛保持。', 1000, flow, '新增：地图 / 编排 / 经验层')

    architecture = arrow('M344 212 H420') + arrow('M772 212 H848')
    architecture += arrow('M1004 284 V328') + arrow('M848 396 H772') + arrow('M420 396 H344')
    architecture += arrow('M196 460 V500 H600 V544', True)
    architecture += box(40, 140, 304, 144, '宿主 / 主编排者', ['事件处 collect；显式会话身份', '无 hooks 仍可检查点调用'], 'new')
    architecture += box(420, 140, 352, 144, '私有根 · 统一权威', ['追加分片 / 不可变正文 / registry', '锁 + 原子替换；视图可重建'], 'new')
    architecture += box(848, 140, 312, 144, '待审候选与回顾', ['本轮保存；自动保存不等于生效', '假设不能驱动执行'], 'new')
    architecture += box(848, 328, 312, 144, '下次明确使用 · 人审', ['先读材料；冻结展示集合', '真实回应核对 → 逐项批准'], 'new')
    architecture += box(420, 328, 352, 144, '少量有效上下文', ['先核状态 / 批准 / 来源 / 依赖', '再匹配范围；应用前再次核查'], 'new')
    architecture += box(40, 328, 304, 144, '原五段流程', ['记录实际应用；独审双重绑定', 'finish 同锁核查并写 done'], 'affected')
    architecture += box(40, 544, 1120, 120, '关闭回退与撤销影响', ['无依赖继续原流程；已有依赖失效只复核相关部分，解除后重新独审；原模板、页面与元数据门槛保留'], 'original')
    architecture += text(40, 708, '范围：受控入口与单一私有根；不承诺同权限伪造检测、外部注入隔离或整根回滚检测；经验层不作调度/进度总线。', 16, SOFT)
    save('memory-architecture', '经验层 · 候选、人审与当前有效性', '从宿主采集到私有候选，下次先读材料再人审，经统一筛选进入原流程；关闭或撤销保留真实依赖。', 800, architecture)


if __name__ == '__main__':
    build()
