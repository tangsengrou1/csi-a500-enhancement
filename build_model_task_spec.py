from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_BREAK
from pathlib import Path


OUT = Path(__file__).resolve().parent / "因子聚合模型统一任务说明.docx"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color="D9D9D9", size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_cell_margins(cell, top=110, start=120, bottom=110, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn("w:" + m))
        if node is None:
            node = OxmlElement("w:" + m)
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


def add_run(paragraph, text, bold=False, color=None, size=None):
    run = paragraph.add_run(text)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if size:
        run.font.size = Pt(size)
    run.font.name = "Arial"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    return run


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.paragraph_format.space_after = Pt(3)
    add_run(p, text)
    return p


def add_number(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.space_after = Pt(4)
    add_run(p, text)
    return p


def add_table(doc, headers, rows, widths=None, font_size=9.2):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for idx, text in enumerate(headers):
        cell = hdr.cells[idx]
        set_cell_shading(cell, "1F4E78")
        set_cell_border(cell)
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        add_run(p, text, bold=True, color="FFFFFF", size=font_size)
        if widths:
            cell.width = Inches(widths[idx])
    for ridx, row in enumerate(rows):
        cells = table.add_row().cells
        for idx, text in enumerate(row):
            cell = cells[idx]
            set_cell_border(cell)
            set_cell_margins(cell)
            if ridx % 2 == 1:
                set_cell_shading(cell, "F3F7FA")
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            add_run(p, str(text), size=font_size)
            if widths:
                cell.width = Inches(widths[idx])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


doc = Document()
sec = doc.sections[0]
sec.top_margin = Inches(0.72)
sec.bottom_margin = Inches(0.70)
sec.left_margin = Inches(0.78)
sec.right_margin = Inches(0.78)
sec.page_width = Inches(8.5)
sec.page_height = Inches(11)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Arial"
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
normal.font.size = Pt(10.5)
normal.font.color.rgb = RGBColor(31, 31, 31)
normal.paragraph_format.line_spacing = 1.18
normal.paragraph_format.space_after = Pt(6)

for name, size, before, after in (("Title", 23, 0, 12), ("Heading 1", 16, 15, 7), ("Heading 2", 12.5, 10, 5), ("Heading 3", 11, 8, 4)):
    st = styles[name]
    st.font.name = "Arial"
    st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    st.font.size = Pt(size)
    st.font.color.rgb = RGBColor(0, 0, 0)
    st.font.bold = True
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

for style_name in ("List Bullet", "List Bullet 2", "List Number"):
    st = styles[style_name]
    st.font.name = "Arial"
    st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    st.font.size = Pt(10.5)

# Cover
p = doc.add_paragraph(style="Title")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(82)
add_run(p, "因子聚合模型统一任务说明", bold=True, size=23)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(26)
add_run(p, "线性模型组  树模型组  组合优化组", color="4F4F4F", size=12)

meta = add_table(doc, ["项目", "内容"], [
    ["文件用途", "统一各模型小组的研究口径、比较标准、输出接口和验收要求"],
    ["适用阶段", "因子库完成后的因子聚合与组合优化衔接阶段"],
    ["版本", "V1.0"],
    ["发布日期", "2026年10月14日"],
    ["维护方式", "由项目负责人统一更新；各小组不得自行改变公共口径"],
], widths=[1.35, 5.45], font_size=9.8)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(20)
p.paragraph_format.space_after = Pt(8)
add_run(p, "核心要求", bold=True, size=12)
p = doc.add_paragraph()
p.paragraph_format.line_spacing = 1.3
add_run(p, "各组可以使用不同的模型结构、正则化方式和训练损失，但必须使用同一预测目标、同一数据版本、同一时间切分、同一评价脚本和同一交易成本假设。最终模型不以单一 IC 最高决定，而以严格样本外、成本后的组合表现与稳定性共同决定。", bold=True)

doc.add_page_break()

doc.add_heading("1 文档目的与最终决策", level=1)
doc.add_paragraph("本阶段的任务是把已经完成的多维因子库聚合为可供组合优化器使用的统一股票预期收益信号。线性模型组与树模型组独立建模，公共评估组按相同协议生成样本外结果，组合优化组在相同约束下比较各模型及其集成方案。")
doc.add_paragraph("项目采用“训练方法可不同，比较口径必须一致”的原则。任何模型若未通过统一数据、样本外验证、成本和风险暴露检查，不得进入最终组合优化。")

doc.add_heading("2 团队分工", level=1)
add_table(doc, ["小组", "主要任务", "不得自行变更", "主要交付"], [
    ["数据与评估组", "冻结数据快照、标签、切分、评价脚本和基准回测", "股票池、时间戳、标签、成本、公共切分", "数据字典、切分文件、统一评分表"],
    ["线性模型组", "建立可解释、低换手的线性聚合模型", "公共输入与测试集；不得查看测试期结果调参", "OOF预测、参数、系数与报告"],
    ["树模型组", "建立可捕捉非线性和交互的树模型", "公共输入与测试集；不得查看测试期结果调参", "OOF预测、参数、重要性与报告"],
    ["组合优化组", "统一缩放模型信号，完成模型集成及约束优化", "风险模型、成本模型和组合约束", "权重、回测、归因和压力测试"],
], widths=[1.05, 2.05, 2.05, 1.65], font_size=8.8)

doc.add_heading("3 统一口径清单", level=1)
doc.add_paragraph("下列项目必须由项目负责人或数据与评估组统一发布。未填写或未冻结前，各模型组只能进行管线开发，不能提交正式结果。")
add_table(doc, ["项目", "统一要求", "冻结值或文件"], [
    ["股票池", "相同市场、板块、上市天数、ST、停牌、涨跌停和流动性过滤规则", "由数据组填写"],
    ["预测时点", "明确每个调仓日的信息截点，所有特征只使用当时可获得的数据", "由数据组填写"],
    ["预测周期 H", "所有模型预测相同持有期的未来收益", "由项目负责人填写"],
    ["标签定义", "明确绝对收益、超额收益或风险中性收益，以及复权和基准定义", "由项目负责人填写"],
    ["调仓频率", "日频、周频或月频只能选择一种正式口径", "由项目负责人填写"],
    ["训练窗口", "固定滚动窗口或扩展窗口，并统一最短训练长度", "由评估组填写"],
    ["成本模型", "统一佣金、印花税、滑点、冲击成本和不可交易处理", "由组合优化组填写"],
    ["风险约束", "统一行业、市值、风格、Beta、个股、行业和换手约束", "由组合优化组填写"],
], widths=[1.15, 4.45, 1.2], font_size=8.8)

doc.add_heading("4 数据与标签要求", level=1)
doc.add_heading("4.1 时间与可得性", level=2)
add_bullet(doc, "所有因子必须采用 as of 口径，以真实公告日、交易日和数据发布时间确定可用时间。")
add_bullet(doc, "禁止使用未来数据补全历史截面；禁止用全样本统计量做标准化、缩尾或缺失值填充。")
add_bullet(doc, "特征处理参数只能在当期训练集估计，再应用到验证集和测试集。")
add_bullet(doc, "若标签持有期重叠，训练集与验证集、验证集与测试集之间必须设置 purge 或 embargo。")

doc.add_heading("4.2 公共预处理", level=2)
add_number(doc, "按统一规则处理异常值和缺失值，并额外保留缺失值指示变量。")
add_number(doc, "按每个交易截面完成行业、市值等公共风险中性化。")
add_number(doc, "输出标准化值和截面排名值两套输入；正式主实验由数据组指定其中一套。")
add_number(doc, "树模型可另做原生输入扩展实验，但扩展实验必须单独标识，不能替代统一输入主实验。")

doc.add_heading("4.3 数据版本", level=2)
doc.add_paragraph("每次正式实验必须记录数据快照版本、因子清单版本、代码提交号、运行时间和随机种子。预测文件中必须保留 security_id、trade_date、label、prediction、model_id 和 fold_id 六个核心字段。")

doc.add_heading("5 统一实验设计", level=1)
doc.add_heading("5.1 两类实验", level=2)
add_table(doc, ["实验", "目的", "训练损失", "结论用途"], [
    ["公共基准实验", "识别模型结构本身的差异", "各组优先使用 MSE 或 Huber 等可比损失", "形成公平基线，不直接决定最终模型"],
    ["组内最优实验", "发挥算法自身优势", "允许使用正则化、Huber、MAE、排序损失等", "进入正式模型比较和集成候选池"],
], widths=[1.25, 2.25, 2.1, 1.2], font_size=9)

doc.add_heading("5.2 线性模型组要求", level=2)
add_bullet(doc, "至少提交 Ridge 与 Elastic Net 两类基准；可扩展 Huber 回归、PLS 或其他有明确说明的线性方法。")
add_bullet(doc, "必须报告系数稳定性、非零因子数量、因子符号变化、共线性处理和正则化路径。")
add_bullet(doc, "主模型应兼顾稳定性、可解释性与低换手，不能只按训练误差选择。")
add_bullet(doc, "超参数只能在内层验证集选择，测试集仅用于一次性外层评估。")

doc.add_heading("5.3 树模型组要求", level=2)
add_bullet(doc, "至少提交一个梯度提升树模型；可扩展随机森林或其他树集成方法。")
add_bullet(doc, "至少比较一个回归损失与一个排序导向损失，说明两者对 IC、换手和尾部预测的影响。")
add_bullet(doc, "必须限制树深、叶节点样本数、学习率和早停，防止复杂度通过测试期结果反向选择。")
add_bullet(doc, "必须提交置换重要性或 SHAP 等解释结果，并检查重要性是否跨窗口稳定。")

doc.add_heading("6 样本外验证协议", level=1)
doc.add_paragraph("正式结果必须来自按时间推进的嵌套滚动验证。禁止随机 K 折，禁止把测试期用于早停、调参或特征筛选。")
add_table(doc, ["层级", "用途", "允许操作", "禁止操作"], [
    ["训练集", "估计参数", "拟合模型、计算预处理参数", "访问未来期统计量"],
    ["内层验证集", "选择超参数", "早停、损失函数和参数选择", "反复试验后汇报为样本外结果"],
    ["外层测试集", "最终评估", "仅生成一次预测并归档", "用于调参、筛因子或改成本假设"],
], widths=[1.1, 1.55, 2.35, 1.8], font_size=9)
doc.add_paragraph("推荐切分结构为扩展窗口或固定长度滚动窗口。例如，用过去若干年训练、下一阶段验证、再下一阶段测试，然后整体向前滚动。具体起止时间由评估组统一发布。所有外层测试预测拼接后形成唯一的 OOF/OOS 预测序列。")

doc.add_heading("7 统一评价体系", level=1)
doc.add_paragraph("模型评估分为预测、信号组合和最终组合三层。单一指标不得直接决定模型胜负。")

doc.add_heading("7.1 第一层 预测质量", level=2)
add_table(doc, ["指标", "用途", "统一计算要求"], [
    ["Pearson IC", "衡量预测值与收益的线性关系", "逐截面计算，再汇总均值、标准差和正值比例"],
    ["Rank IC", "衡量排序能力，对极端值更稳健", "逐截面 Spearman 相关；排序选股的主指标之一"],
    ["ICIR 与 Rank ICIR", "衡量跨期稳定性", "基于完整样本外 IC 序列；同时报告滚动值和自相关稳健结果"],
    ["样本外 R2 或预测损失", "衡量数值预测能力", "使用统一基准预测与统一权重"],
    ["分组稳定性", "识别模型失效区域", "按年份、市场状态、市值和行业分别报告"],
], widths=[1.35, 2.2, 3.25], font_size=9)

doc.add_heading("7.2 第二层 信号组合表现", level=2)
add_bullet(doc, "使用相同分组、相同持有期、相同加权方式形成多空或多头组合。")
add_bullet(doc, "必须同时报告成本前后收益、年化波动、Sharpe、最大回撤、换手、胜率和容量指标。")
add_bullet(doc, "分别报告多头端与空头端，避免总收益掩盖单侧不可实现的问题。")
add_bullet(doc, "报告行业、市值、Beta 和主要风格暴露，确认收益并非来自未控制的系统性偏离。")

doc.add_heading("7.3 第三层 最终组合表现", level=2)
doc.add_paragraph("组合优化组在完全相同的风险模型、成本模型和约束下，分别输入线性信号、树模型信号和集成信号。最终选择以样本外成本后信息比率或预先确定的组合效用为主，同时检查回撤、换手、容量和跨期稳定性。")

doc.add_heading("7.4 模型选择原则", level=2)
add_number(doc, "先通过有效性门槛：样本外 IC 方向正确，跨期稳定，风险暴露和换手处于允许范围。")
add_number(doc, "再比较经济价值：在相同成本和约束下比较净信息比率、净 Sharpe 或预先冻结的效用函数。")
add_number(doc, "若两个模型表现接近，优先选择更稳定、换手更低、解释性更强的模型，或进入集成。")
add_number(doc, "不得依据某一个样本区间内最高的 IC、Rank IC 或 ICIR 单独定胜负。")

doc.add_heading("8 模型输出与集成接口", level=1)
doc.add_heading("8.1 标准预测文件", level=2)
add_table(doc, ["字段", "类型", "说明"], [
    ["security_id", "string", "统一证券标识"],
    ["trade_date", "date", "预测形成日"],
    ["target_end_date", "date", "标签持有期结束日"],
    ["prediction_raw", "float", "模型原始预测"],
    ["prediction_rank", "float", "当期截面百分位排名"],
    ["prediction_z", "float", "当期截面标准分，按统一截断规则处理"],
    ["label", "float", "统一标签；测试期结束后由评估脚本合并"],
    ["model_id", "string", "模型族、版本、损失和关键配置的唯一编号"],
    ["fold_id", "string", "外层测试折编号"],
    ["train_end_date", "date", "本次模型所使用数据的最后日期"],
], widths=[1.35, 1.0, 4.45], font_size=8.7)

doc.add_heading("8.2 集成规则", level=2)
doc.add_paragraph("线性模型和树模型的原始输出不可直接相加。组合优化组先在每个截面把模型输出统一转为百分位排名或截面标准分，再进行集成。首个正式基准使用 50比50 权重；动态权重或二层模型只能使用历史 OOF 预测估计。")
add_bullet(doc, "二层模型输入只能是第一层模型的样本外预测。")
add_bullet(doc, "集成权重建议设置非负、和为一，并对权重变化设置收缩或换手约束。")
add_bullet(doc, "必须同时报告单模型与集成模型，不能只提交表现最好的集成结果。")

doc.add_heading("9 统一交付物", level=1)
add_table(doc, ["交付物", "最低内容", "验收条件"], [
    ["模型说明", "目标、特征、预处理、损失、参数空间、随机种子", "他人可据此复现"],
    ["运行代码", "训练、预测、评价脚本及环境说明", "从冻结数据可一键或按明确步骤运行"],
    ["配置文件", "所有公共参数和模型参数", "不在代码中散落硬编码"],
    ["OOF预测", "符合第8节字段规范的完整样本外记录", "主键唯一、无测试期泄漏、覆盖率达标"],
    ["模型对象", "每个外层窗口对应的已训练模型", "版本与预测文件一致"],
    ["结果报告", "统一指标、分期结果、风险暴露、换手、成本和稳定性", "使用公共评价脚本生成"],
    ["异常清单", "缺失、停牌、无法交易、数据修订和运行失败记录", "问题可追踪且处理规则一致"],
], widths=[1.3, 3.45, 2.05], font_size=8.8)

doc.add_heading("10 文件结构与命名", level=1)
p = doc.add_paragraph()
p.paragraph_format.left_indent = Inches(0.25)
for line in [
    "project/",
    "  data_version/",
    "  splits/",
    "  configs/",
    "  models/linear/<model_id>/",
    "  models/tree/<model_id>/",
    "  predictions/<model_id>/",
    "  evaluation/<model_id>/",
    "  portfolio/<model_id>/",
    "  logs/<run_id>/",
]:
    r = add_run(p, line, size=9.5)
    r.font.name = "Menlo"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.add_break()
doc.add_paragraph("建议 model_id 采用 model_family loss feature_version target_horizon run_version 的组合，确保预测、模型、配置和报告可以一一对应。")

doc.add_heading("11 验收检查表", level=1)
check_rows = [
    ["□", "使用冻结的数据快照、标签和股票池"],
    ["□", "所有特征满足真实可得时间要求，无未来数据"],
    ["□", "仅用训练集估计预处理参数"],
    ["□", "严格执行统一滚动切分和 purge 或 embargo"],
    ["□", "测试集未用于早停、调参、特征筛选或成本设定"],
    ["□", "提交完整 OOF 预测及唯一 model_id"],
    ["□", "使用公共脚本计算 IC、Rank IC、ICIR、换手和成本后绩效"],
    ["□", "报告分年份、分市值、分行业和市场状态稳定性"],
    ["□", "报告风险暴露、多头端、空头端和不可交易处理"],
    ["□", "代码、配置、随机种子和运行日志齐全，可复现"],
]
add_table(doc, ["确认", "验收项目"], check_rows, widths=[0.8, 6.0], font_size=9.2)

doc.add_heading("12 结果汇报模板", level=1)
doc.add_paragraph("每个模型只填写一行，所有数值来自公共评价脚本。未达到正式测试条件的实验标为“研究实验”，不得与正式结果混排。")
add_table(doc, ["模型", "损失", "Rank IC", "Rank ICIR", "成本后 IR", "换手", "最大回撤", "结论"], [
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", ""],
], widths=[1.0, 0.8, 0.8, 0.85, 0.85, 0.65, 0.85, 1.0], font_size=7.9)

doc.add_heading("13 必须在正式实验前确认的事项", level=1)
doc.add_paragraph("项目负责人应在正式开跑前签字或在版本库中确认下列内容：预测周期、标签定义、调仓频率、股票池、训练窗口、交易成本、风险约束、主评价指标、有效性门槛和最终效用函数。以上任何一项变更都应形成新版本，并要求所有候选模型按新版本重新评价。")

# Footer with page number field
footer = sec.footer
p = footer.paragraphs[0]
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(4)
add_run(p, "因子聚合模型统一任务说明  |  ", color="777777", size=8)
run = p.add_run()
fld_char1 = OxmlElement("w:fldChar")
fld_char1.set(qn("w:fldCharType"), "begin")
instr = OxmlElement("w:instrText")
instr.set(qn("xml:space"), "preserve")
instr.text = "PAGE"
fld_char2 = OxmlElement("w:fldChar")
fld_char2.set(qn("w:fldCharType"), "end")
run._r.append(fld_char1)
run._r.append(instr)
run._r.append(fld_char2)

# Set keep-together behavior for headings and reasonable paragraph widow control
for p in doc.paragraphs:
    p_pr = p._p.get_or_add_pPr()
    widow = OxmlElement("w:widowControl")
    p_pr.append(widow)

doc.core_properties.title = "因子聚合模型统一任务说明"
doc.core_properties.subject = "线性模型、树模型与组合优化的统一任务与验收标准"
doc.core_properties.author = "项目组"
doc.save(OUT)
print(OUT)
