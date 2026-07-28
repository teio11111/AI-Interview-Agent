"""综合元评估报告 PDF 生成器

支持中文字体（自动寻找系统字体，跨 Windows/Linux 部署）。
"""
import io
import os
import platform
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# =================== 字体加载（跨平台兼容） ===================

_FONT_REGISTERED = False
_FONT_NAME = None
_FONT_BOLD_NAME = None


def _find_chinese_font_path():
    """跨平台寻找中文字体 TTF 路径。优先 ttf（reportlab 对 ttc 集合字体支持不佳）。"""
    system = platform.system()

    # 候选文件（按优先级）
    candidates = []

    if system == 'Windows':
        win = 'C:/Windows/Fonts'
        candidates.extend([
            os.path.join(win, 'simhei.ttf'),          # 黑体（轻量、清晰）
            os.path.join(win, 'simkai.ttf'),          # 楷体
            os.path.join(win, 'simfang.ttf'),         # 仿宋
            os.path.join(win, 'simsun.ttc'),          # 宋体集合
            os.path.join(win, 'msyh.ttc'),            # 微软雅黑集合
        ])
    else:
        # Linux / macOS / Docker 部署
        candidates.extend([
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # 兜底（不含中文）
            '/System/Library/Fonts/PingFang.ttc',     # macOS
            '/System/Library/Fonts/STHeiti Light.ttc',
        ])

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


def _ensure_font_registered():
    """确保中文字体已注册到 reportlab（只注册一次）"""
    global _FONT_REGISTERED, _FONT_NAME, _FONT_BOLD_NAME

    if _FONT_REGISTERED:
        return

    font_path = _find_chinese_font_path()

    if font_path:
        try:
            # 注册常规字体
            pdfmetrics.registerFont(TTFont('CN', font_path))
            _FONT_NAME = 'CN'
            _FONT_BOLD_NAME = 'CN'
            # 如果文件名包含 Bold/Black，再尝试注册粗体变体
            base = os.path.basename(font_path).lower()
            if 'simhei' in base or 'noto' in base or 'wqy' in base:
                bold_candidate = font_path.replace('simhei', 'simhei_bold')  # placeholder
                # 实际只有一份字体的，bold 用同一份即可（粗体用样式加粗不精确但可用）
        except Exception:
            _FONT_NAME = 'Helvetica'
            _FONT_BOLD_NAME = 'Helvetica-Bold'
    else:
        # 找不到任何中文字体，回退到 Helvetica（中文会显示为方块）
        _FONT_NAME = 'Helvetica'
        _FONT_BOLD_NAME = 'Helvetica-Bold'

    _FONT_REGISTERED = True


# =================== 样式定义 ===================

def _get_styles():
    """构建文档样式表"""
    _ensure_font_registered()
    styles = getSampleStyleSheet()

    # 标题
    styles.add(ParagraphStyle(
        name='CN_Title', fontName=_FONT_NAME, fontSize=22, leading=28,
        alignment=TA_CENTER, spaceAfter=14, textColor=colors.HexColor('#1a1a2e'),
    ))
    styles.add(ParagraphStyle(
        name='CN_SubTitle', fontName=_FONT_NAME, fontSize=12, leading=16,
        alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor('#555'),
    ))
    styles.add(ParagraphStyle(
        name='CN_H1', fontName=_FONT_NAME, fontSize=15, leading=20,
        spaceBefore=12, spaceAfter=6, textColor=colors.HexColor('#1a73e8'),
        borderPadding=4, borderWidth=0, leftIndent=0,
    ))
    styles.add(ParagraphStyle(
        name='CN_H2', fontName=_FONT_NAME, fontSize=12, leading=16,
        spaceBefore=8, spaceAfter=4, textColor=colors.HexColor('#333'),
    ))
    styles.add(ParagraphStyle(
        name='CN_Body', fontName=_FONT_NAME, fontSize=10, leading=14,
        spaceAfter=4, textColor=colors.HexColor('#222'),
    ))
    styles.add(ParagraphStyle(
        name='CN_Small', fontName=_FONT_NAME, fontSize=8, leading=11,
        textColor=colors.HexColor('#666'),
    ))
    styles.add(ParagraphStyle(
        name='CN_Bullet', fontName=_FONT_NAME, fontSize=10, leading=14,
        leftIndent=14, bulletIndent=4, spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name='CN_Quote', fontName=_FONT_NAME, fontSize=10, leading=14,
        leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=4,
        backColor=colors.HexColor('#f5f5f5'), borderPadding=6,
        textColor=colors.HexColor('#333'),
    ))
    styles.add(ParagraphStyle(
        name='CN_Header', fontName=_FONT_NAME, fontSize=8, leading=10,
        textColor=colors.HexColor('#888'), alignment=TA_CENTER,
    ))

    return styles


# =================== 工具函数 ===================

def _color_for_recommendation(rec):
    """根据推荐等级返回颜色"""
    return {
        '强烈推荐': colors.HexColor('#198754'),
        '推荐': colors.HexColor('#0d6efd'),
        '有条件推荐': colors.HexColor('#fd7e14'),
        '不推荐': colors.HexColor('#dc3545'),
        '强烈不推荐': colors.HexColor('#842029'),
    }.get(rec, colors.HexColor('#6c757d'))


def _color_for_score(score):
    """根据综合分返回颜色"""
    if score >= 85:
        return colors.HexColor('#198754')
    if score >= 70:
        return colors.HexColor('#0d6efd')
    if score >= 60:
        return colors.HexColor('#fd7e14')
    if score >= 50:
        return colors.HexColor('#dc3545')
    return colors.HexColor('#842029')


def _color_for_verdict(verdict):
    """根据跨阶段判定返回颜色"""
    return {
        '一致': colors.HexColor('#198754'),
        '不一致': colors.HexColor('#dc3545'),
        '部分一致': colors.HexColor('#fd7e14'),
    }.get(verdict, colors.HexColor('#6c757d'))


def _color_for_severity(sev):
    """根据风险严重度返回颜色"""
    return {
        '高': colors.HexColor('#dc3545'),
        '中': colors.HexColor('#fd7e14'),
        '低': colors.HexColor('#0dcaf0'),
    }.get(sev, colors.HexColor('#6c757d'))


def _safe_text(s):
    """过滤可能干扰 reportlab 的字符（保留换行/常规标点）"""
    if not s:
        return ''
    return str(s).replace('\r\n', '\n').strip()


def _esc(s):
    """转义 reportlab paragraph 中需要转义的字符"""
    if s is None:
        return ''
    s = str(s)
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# =================== 文档模板（页眉页脚） ===================

class _MetaEvalDoc(BaseDocTemplate):
    """自定义文档模板，支持页眉页脚"""

    def __init__(self, *args, candidate_name='', position_name='', **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate_name = candidate_name
        self.position_name = position_name

    def afterFlowable(self, flowable):
        # 不需要此方法，留作扩展
        pass


def _on_page(canvas, doc):
    """页眉页脚绘制"""
    canvas.saveState()

    # 页眉
    canvas.setFont(_FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor('#888'))
    header_text = f'综合元评估报告 · {doc.candidate_name} · {doc.position_name}'
    canvas.drawString(2 * cm, A4[1] - 1.2 * cm, header_text)
    canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)

    # 页脚
    canvas.setFont(_FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor('#888'))
    footer_text = f'第 {doc.page} 页'
    canvas.drawCentredString(A4[0] / 2, 1.2 * cm, footer_text)

    # 右下角：生成时间
    gen_time = getattr(canvas, '_gen_time', '')
    if gen_time:
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'生成于 {gen_time}')

    canvas.restoreState()


# =================== 主体生成 ===================

def generate_meta_evaluation_pdf(candidate_dict, position_dict, evaluation_dict, computation=None):
    """生成综合元评估报告 PDF 字节流

    Args:
        candidate_dict: 候选人 dict（含 name / id 等）
        position_dict: 岗位 dict（含 name / tech_requirements 等）
        evaluation_dict: 综合元评估 dict（含 overall_score / final_recommendation 等）
        computation: 调试字段，可选（含 penalty / raw_score / final_score 等）

    Returns:
        bytes: PDF 文件二进制内容
    """
    _ensure_font_registered()

    buf = io.BytesIO()
    candidate_name = _safe_text(candidate_dict.get('name', ''))
    position_name = _safe_text(position_dict.get('name', '')) if position_dict else ''

    doc = _MetaEvalDoc(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.2 * cm, bottomMargin=2 * cm,
        title=f'综合元评估报告-{candidate_name}',
        author='AI Interview Agent',
        candidate_name=candidate_name,
        position_name=position_name,
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='normal',
        showBoundary=0,
    )
    template = PageTemplate(id='default', frames=frame, onPage=_on_page)
    doc.addPageTemplates([template])

    styles = _get_styles()
    story = []

    # ===== 封面区（标题 + 元信息）=====
    story.append(Paragraph('综合元评估报告', styles['CN_Title']))
    story.append(Paragraph(
        f'候选人 <b>{_esc(candidate_name)}</b> · 应聘岗位 <b>{_esc(position_name)}</b>',
        styles['CN_SubTitle']
    ))

    score = evaluation_dict.get('overall_score', 0) or 0
    rec = evaluation_dict.get('final_recommendation', '未评估')
    rationale = evaluation_dict.get('decision_rationale', '') or ''

    story.append(Spacer(1, 6 * mm))

    # 综合分 + 推荐等级卡片
    score_color = _color_for_score(score)
    rec_color = _color_for_recommendation(rec)

    cover_table = Table(
        [[
            Paragraph(f'<para align="center"><font size="36" color="{score_color.hexval()}"><b>{score}</b></font><br/><font size="10" color="#555">综合分（0-100）</font></para>', styles['CN_Body']),
            Paragraph(f'<para align="center"><font size="14" color="{rec_color.hexval()}"><b>{_esc(rec)}</b></font><br/><font size="10" color="#555">推荐等级</font></para>', styles['CN_Body']),
        ]],
        colWidths=[8 * cm, 8 * cm],
        rowHeights=[3 * cm],
    )
    cover_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#fafbff')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fffbf5')),
    ]))
    story.append(cover_table)

    story.append(Spacer(1, 6 * mm))

    # 决策理由
    if rationale:
        story.append(Paragraph('<b>决策理由：</b>' + _esc(rationale), styles['CN_Quote']))

    # 报告生成时间
    story.append(Paragraph(
        f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        styles['CN_Small']
    ))

    story.append(Spacer(1, 4 * mm))

    # ===== 1. 五维评分 =====
    story.append(Paragraph('一、五维评分', styles['CN_H1']))
    dims = evaluation_dict.get('dimension_scores', {}) or {}
    label_map = {
        'technical_ability': '技术能力',
        'project_experience': '项目经验',
        'system_design': '系统设计',
        'communication': '沟通表达',
        'learning_potential': '学习潜力',
    }

    if dims:
        dim_rows = [['维度', '评分（0-10）', '评估']]
        for k, v in dims.items():
            label = label_map.get(k, k)
            try:
                score_num = float(v) if v is not None else 0
            except (TypeError, ValueError):
                score_num = 0
            score_num = max(0, min(10, score_num))
            if score_num >= 7:
                tag = '✓ 优秀'
            elif score_num >= 5:
                tag = '○ 合格'
            else:
                tag = '× 待提升'
            dim_rows.append([label, f'{score_num:.1f}', tag])

        dim_table = Table(dim_rows, colWidths=[5 * cm, 4 * cm, 4 * cm])
        dim_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), _FONT_NAME, 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a73e8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(dim_table)
    else:
        story.append(Paragraph('（无五维评分数据）', styles['CN_Body']))

    story.append(Spacer(1, 6 * mm))

    # ===== 2. 核心优势 =====
    strengths = evaluation_dict.get('key_strengths', []) or []
    story.append(Paragraph('二、核心优势', styles['CN_H1']))
    if strengths:
        for i, s in enumerate(strengths, 1):
            if isinstance(s, dict):
                point = _esc(s.get('point', ''))
                evidence = _esc(s.get('evidence', ''))
                relevance = _esc(s.get('relevance', ''))
                story.append(Paragraph(f'<b>{i}. {point}</b>', styles['CN_H2']))
                if evidence:
                    story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;📌 证据：{evidence}', styles['CN_Body']))
                if relevance:
                    story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;🎯 岗位相关性：{relevance}', styles['CN_Body']))
            else:
                story.append(Paragraph(f'<b>{i}. {_esc(s)}</b>', styles['CN_Body']))
    else:
        story.append(Paragraph('（未提取出明确优势）', styles['CN_Body']))

    story.append(Spacer(1, 4 * mm))

    # ===== 3. 关键风险 =====
    risks = evaluation_dict.get('key_risks', []) or []
    story.append(Paragraph('三、关键风险', styles['CN_H1']))
    if risks:
        for i, r in enumerate(risks, 1):
            if isinstance(r, dict):
                risk = _esc(r.get('risk', ''))
                sev = _esc(r.get('severity', ''))
                evidence = _esc(r.get('evidence', ''))
                mitigation = _esc(r.get('mitigation', ''))
                sev_color = _color_for_severity(sev).hexval()
                sev_html = f'<font color="{sev_color}"><b>[{sev}风险]</b></font>' if sev else ''
                story.append(Paragraph(f'<b>{i}. {sev_html}{risk}</b>', styles['CN_H2']))
                if evidence:
                    story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;⚠ 证据：{evidence}', styles['CN_Body']))
                if mitigation:
                    story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;✓ 规避建议：{mitigation}', styles['CN_Body']))
            else:
                story.append(Paragraph(f'<b>{i}. {_esc(r)}</b>', styles['CN_Body']))
    else:
        story.append(Paragraph('（未识别出明显风险）', styles['CN_Body']))

    story.append(Spacer(1, 6 * mm))

    # ===== 4. 跨阶段交叉验证 =====
    cross = evaluation_dict.get('cross_stage_analysis', {}) or {}
    findings = cross.get('consistency_findings', []) or []
    validated = cross.get('validated_conclusions', []) or []
    alerts = cross.get('inconsistency_alerts', []) or []

    story.append(Paragraph('四、跨阶段交叉验证', styles['CN_H1']))

    if findings:
        find_rows = [['简历/评估结论', '面试表现', '判定', '影响']]
        for f in findings:
            if not isinstance(f, dict):
                continue
            claim = _esc(f.get('claim', '-'))
            evidence = _esc(f.get('interview_evidence', '-'))
            verdict = _esc(f.get('verdict', '-'))
            impact = _esc(f.get('impact', ''))
            verdict_color = _color_for_verdict(f.get('verdict', '')).hexval()
            verdict_html = f'<font color="{verdict_color}"><b>{verdict}</b></font>' if verdict else '-'
            find_rows.append([
                Paragraph(claim, styles['CN_Small']),
                Paragraph(evidence, styles['CN_Small']),
                Paragraph(verdict_html, styles['CN_Small']),
                Paragraph(impact, styles['CN_Small']),
            ])

        find_table = Table(find_rows, colWidths=[4.5 * cm, 4.5 * cm, 2 * cm, 5 * cm])
        find_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), _FONT_NAME, 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a73e8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(find_table)
    else:
        story.append(Paragraph('（无跨阶段一致性结论）', styles['CN_Body']))

    if validated:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph('<b>✓ 在面试中得到确认的简历评估结论：</b>', styles['CN_Body']))
        for v in validated[:8]:
            story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;• {_esc(v)}', styles['CN_Bullet']))

    if alerts:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph('<b><font color="#dc3545">⚠ 简历与实际不符之处：</font></b>', styles['CN_Body']))
        for a in alerts[:8]:
            story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;• {_esc(a)}', styles['CN_Bullet']))

    story.append(Spacer(1, 6 * mm))

    # ===== 5. 多轮面试追踪 =====
    multi = evaluation_dict.get('multi_round_tracking', {}) or {}
    rounds = multi.get('round_summary', []) or []

    if rounds:
        story.append(Paragraph('五、多轮面试追踪', styles['CN_H1']))

        round_rows = [['轮次', '侧重点', '评分', '关键发现']]
        for r in rounds:
            if not isinstance(r, dict):
                continue
            round_rows.append([
                Paragraph(f'<b>第{_esc(r.get("round", "?"))}轮</b>', styles['CN_Small']),
                Paragraph(_esc(r.get('focus', '-')), styles['CN_Small']),
                Paragraph(f'{_esc(r.get("score", "?"))} 分', styles['CN_Small']),
                Paragraph(_esc(r.get('key_findings', '-')), styles['CN_Small']),
            ])

        round_table = Table(round_rows, colWidths=[2 * cm, 4.5 * cm, 2 * cm, 7.5 * cm])
        round_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), _FONT_NAME, 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a73e8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(round_table)

        progression = multi.get('progression', '')
        if progression:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                f'<b>进步趋势：</b>{_esc(progression)} · {_esc(multi.get("progression_detail", ""))}',
                styles['CN_Body']
            ))

        consensus = multi.get('consensus_across_rounds', '')
        if consensus:
            story.append(Paragraph(
                f'<b>多轮结论：</b>{_esc(consensus)}',
                styles['CN_Body']
            ))

        story.append(Spacer(1, 4 * mm))

    # ===== 6. 入职建议 =====
    onboarding = evaluation_dict.get('onboarding_suggestions', {}) or {}
    if onboarding.get('if_hired') or onboarding.get('first_90_days'):
        story.append(Paragraph('六、入职建议', styles['CN_H1']))
        if_hired = _esc(onboarding.get('if_hired', ''))
        first_90 = _esc(onboarding.get('first_90_days', ''))

        onb_rows = [[
            Paragraph(f'<b>入职后关注点</b><br/><br/>{if_hired}', styles['CN_Body']),
            Paragraph(f'<b>前 90 天建议</b><br/><br/>{first_90}', styles['CN_Body']),
        ]]
        onb_table = Table(onb_rows, colWidths=[8 * cm, 8 * cm])
        onb_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dee2e6')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#fafbff')),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fffbf5')),
        ]))
        story.append(onb_table)
        story.append(Spacer(1, 4 * mm))

    # ===== 7. 给候选人的反馈 =====
    candidate_msg = _safe_text(evaluation_dict.get('candidate_message', ''))
    if candidate_msg:
        story.append(Paragraph('七、给候选人的综合反馈', styles['CN_H1']))
        story.append(Paragraph(candidate_msg, styles['CN_Quote']))

    # ===== 8. 综合评估总结 =====
    summary = _safe_text(evaluation_dict.get('summary', ''))
    if summary:
        story.append(Paragraph('八、综合评估总结', styles['CN_H1']))
        story.append(Paragraph(summary, styles['CN_Body']))

    # ===== 9. 计算说明（调试字段，可选）=====
    if computation:
        comp_lines = []
        if computation.get('raw_score') is not None:
            comp_lines.append(f'加权原始分：{computation["raw_score"]}')
        if computation.get('penalty') is not None:
            comp_lines.append(f'跨阶段一致性扣分：-{computation["penalty"]} 分')
        if computation.get('final_score') is not None:
            comp_lines.append(f'最终综合分：{computation["final_score"]} 分')
        if computation.get('resume_weight') is not None:
            comp_lines.append(
                f'权重方案：简历 {int(computation["resume_weight"]*100)}% + '
                f'各轮面试 {int((1-computation["resume_weight"])*100)}%'
            )

        if comp_lines:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph('<b>📐 评分计算说明</b>', styles['CN_H2']))
            for line in comp_lines:
                story.append(Paragraph(f'&nbsp;&nbsp;&nbsp;&nbsp;• {_esc(line)}', styles['CN_Small']))

    # ===== 10. 报告说明页脚 =====
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        '────────────── 📋 报告说明 ──────────────',
        styles['CN_Small']
    ))
    story.append(Paragraph(
        '本报告由 AI Interview Agent 多智能体协作系统自动生成，综合了：',
        styles['CN_Small']
    ))
    story.append(Paragraph(
        '&nbsp;&nbsp;&nbsp;&nbsp;• 岗位画像分析（3+1 协作）<br/>'
        '&nbsp;&nbsp;&nbsp;&nbsp;• 简历评估（3+1 协作）<br/>'
        '&nbsp;&nbsp;&nbsp;&nbsp;• 各轮面试评价（每轮 3+1 协作）<br/>'
        '&nbsp;&nbsp;&nbsp;&nbsp;• 跨阶段一致性验证与综合打分',
        styles['CN_Small']
    ))
    story.append(Paragraph(
        '最终综合分采用预设权重方案（简历 15-35% + 面试评价 65-85%）+ '
        '跨阶段一致性惩罚（最高 25 分），系统自动计算并应用。',
        styles['CN_Small']
    ))

    # 写入页脚的生成时间
    import time
    doc._gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 保存生成时间供页脚使用
    import builtins
    orig_init = _on_page
    def _on_page_with_time(canvas, doc):
        canvas._gen_time = doc._gen_time
        orig_init(canvas, doc)
    # 替换模板的 onPage
    template.onPage = _on_page_with_time

    doc.build(story)
    return buf.getvalue()