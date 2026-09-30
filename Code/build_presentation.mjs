import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKILL_DIR = process.env.OAI_PRESENTATION_SKILL_DIR;
const RUNTIME_PYTHON = process.env.OAI_RUNTIME_PYTHON ?? "python3";
if (!SKILL_DIR) {
  throw new Error("Set OAI_PRESENTATION_SKILL_DIR before rebuilding the presentation template.");
}
const TMP_DIR = path.join(ROOT, ".pptx-build");
const FINAL_PPTX = path.join(ROOT, "Presentation", "中证A500指数增强基金课堂汇报模板.pptx");
await fs.mkdir(TMP_DIR, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const FONT = "Arial Unicode MS";
const C = { navy: "#163A5F", blue: "#2E6F9E", pale: "#EAF2F8", ink: "#15202B", gray: "#66737F", light: "#D9E2E8", white: "#FFFFFF", amber: "#C17A19" };

function addText(slide, text, x, y, w, h, size = 22, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill ?? "none",
    line: { fill: opts.line ?? "none", width: opts.lineWidth ?? 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: size,
    bold: opts.bold ?? false,
    color: opts.color ?? C.ink,
    alignment: opts.align ?? "left",
    verticalAlignment: opts.valign ?? "middle",
    autoFit: "shrinkText",
  };
  return shape;
}

function baseSlide(title, number) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addText(slide, title, 64, 32, 1100, 58, 32, { bold: true, color: C.navy });
  addText(slide, String(number).padStart(2, "0"), 1175, 35, 50, 35, 14, { align: "right", color: C.gray });
  slide.shapes.add({ geometry: "rect", position: { left: 64, top: 99, width: 1152, height: 3 }, fill: C.blue, line: { fill: "none", width: 0 } });
  return slide;
}

function addBullets(slide, items, x = 88, y = 150, w = 1080, size = 23, gap = 70) {
  items.forEach((item, i) => {
    slide.shapes.add({ geometry: "ellipse", position: { left: x, top: y + i * gap + 12, width: 10, height: 10 }, fill: C.blue, line: { fill: "none", width: 0 } });
    addText(slide, item, x + 28, y + i * gap, w - 28, 54, size);
  });
}

// 1 Cover
{
  const slide = presentation.slides.add();
  slide.background.fill = C.navy;
  addText(slide, "中证 A500 指数增强基金设计", 90, 185, 1100, 100, 44, { bold: true, color: C.white, align: "center" });
  addText(slide, "多因子观点  Black-Litterman  约束优化", 160, 300, 960, 56, 23, { color: "#D8E7F2", align: "center" });
  addText(slide, "第一次小组作业  第    组", 300, 500, 680, 44, 18, { color: C.white, align: "center" });
}

// 2
{
  const s = baseSlide("研究问题与硬约束", 2);
  addBullets(s, ["目标：在控制相对风险的前提下获取稳定超额收益", "调仓：周频信号，下一交易日执行", "风险：年化预期跟踪误差不超过 6%", "交易：多头、行业偏离受控、单周单边换手率不超过 20%"]);
  addText(s, "所有正式结论均以 Wind 历史时点数据为依据", 160, 590, 960, 55, 21, { fill: C.pale, align: "center", bold: true, color: C.navy });
}

// 3
{
  const s = baseSlide("中证 A500 与指数增强基金", 3);
  addText(s, "指数特征", 90, 150, 280, 48, 25, { bold: true, color: C.blue });
  addText(s, "正式报告补充编制方案、行业覆盖、权重规则与调整机制", 90, 205, 470, 120, 21, { fill: C.pale });
  addText(s, "增强收益来源", 650, 150, 300, 48, 25, { bold: true, color: C.blue });
  addText(s, "股票选择、风险预算、交易执行与成本控制", 650, 205, 470, 120, 21, { fill: C.pale });
  addText(s, "产品比较", 90, 405, 280, 48, 25, { bold: true, color: C.blue });
  addText(s, "选取可比基金，核验投资范围、费率、规模与跟踪目标", 90, 460, 1030, 105, 21, { fill: "#F5F7F9" });
}

// 4
{
  const s = baseSlide("数据口径与防前视处理", 4);
  const rows = [
    ["历史成分与权重", "只使用信号日前最近生效快照"],
    ["行情与交易状态", "信号日收盘后计算，次日执行"],
    ["财务指标", "公告日后的下一交易日起生效"],
    ["行业分类", "按历史生效日期向后匹配"],
  ];
  rows.forEach((r, i) => {
    addText(s, r[0], 100, 145 + i * 102, 310, 68, 21, { bold: true, color: C.white, fill: C.navy, align: "center" });
    addText(s, r[1], 410, 145 + i * 102, 720, 68, 21, { fill: i % 2 ? "#F4F7F9" : C.pale });
  });
  addText(s, "数据审计失败时停止回测，不修改原始 Wind 数值", 180, 595, 920, 46, 19, { bold: true, color: C.amber, align: "center" });
}

// 5
{
  const s = baseSlide("策略流程", 5);
  const labels = ["Wind 数据", "因子标准化", "滚动 ICIR", "BL 后验收益", "约束优化", "周频回测"];
  labels.forEach((label, i) => {
    const x = 70 + i * 195;
    addText(s, label, x, 275, 155, 92, 20, { bold: true, color: i === 5 ? C.white : C.navy, fill: i === 5 ? C.blue : C.pale, align: "center" });
    if (i < labels.length - 1) addText(s, "›", x + 158, 288, 35, 60, 34, { color: C.blue, align: "center" });
  });
  addText(s, "每个调仓日保存目标权重、实际权重、约束结果与优化状态", 170, 465, 940, 60, 21, { align: "center", color: C.gray });
}

// 6
{
  const s = baseSlide("四类因子与有效性检验", 6);
  const factors = [["价值", "EP  BP  SP  股息率"], ["质量", "ROE  毛利率  现金流质量  低杠杆"], ["动量", "过去 12 个月剔除最近 1 个月"], ["低波动", "近 60 日波动率与下行波动率"]];
  factors.forEach((f, i) => {
    const y = 145 + i * 105;
    addText(s, f[0], 95, y, 210, 72, 23, { bold: true, color: C.white, fill: C.blue, align: "center" });
    addText(s, f[1], 305, y, 820, 72, 22, { fill: i % 2 ? "#F4F7F9" : C.pale });
  });
  addText(s, "报告覆盖率、Rank IC、ICIR、分组收益、换手率与因子相关性", 130, 595, 1020, 45, 19, { align: "center", color: C.gray });
}

// 7
{
  const s = baseSlide("Black-Litterman 观点融合", 7);
  addText(s, "市场均衡收益", 95, 180, 300, 80, 24, { bold: true, color: C.navy, fill: C.pale, align: "center" });
  addText(s, "+", 420, 190, 50, 55, 32, { color: C.blue, align: "center" });
  addText(s, "多因子相对收益观点", 495, 180, 330, 80, 24, { bold: true, color: C.navy, fill: C.pale, align: "center" });
  addText(s, "=", 850, 190, 50, 55, 32, { color: C.blue, align: "center" });
  addText(s, "后验预期收益", 925, 180, 260, 80, 24, { bold: true, color: C.white, fill: C.blue, align: "center" });
  addBullets(s, ["基准权重与协方差矩阵生成均衡先验", "观点置信度由滚动 IC 稳定性确定", "完整策略与不使用 BL 的组合进行对照"], 125, 350, 1030, 21, 66);
}

// 8
{
  const s = baseSlide("组合约束与交易规则", 8);
  const items = [["跟踪误差", "≤ 6%"], ["行业主动偏离", "≤ ±2 个百分点"], ["个股主动偏离", "≤ ±1 个百分点"], ["单周单边换手", "≤ 20%"], ["交易成本", "主结果 20bp"]];
  items.forEach((it, i) => {
    const x = i % 2 === 0 ? 110 : 670;
    const y = 145 + Math.floor(i / 2) * 140;
    addText(s, it[0], x, y, 275, 74, 21, { fill: C.pale, bold: true, color: C.navy });
    addText(s, it[1], x + 275, y, 190, 74, 24, { fill: C.navy, bold: true, color: C.white, align: "center" });
  });
}

// 9
{
  const s = baseSlide("正式回测绩效", 9);
  addText(s, "导入 Wind 数据并运行正式回测后，在此插入净值与累计超额收益图", 120, 170, 1040, 230, 25, { fill: "#F4F7F9", align: "center", color: C.gray });
  addText(s, "必报指标", 120, 455, 200, 44, 23, { bold: true, color: C.blue });
  addText(s, "年化收益  年化超额收益  Sharpe  最大回撤  信息比率  实现跟踪误差", 120, 510, 1040, 80, 21, { fill: C.pale, align: "center" });
  s.speakerNotes.textFrame.setText("本页不得使用 Result/demo 中的合成结果。正式图表从 Result/official 生成。 ");
}

// 10
{
  const s = baseSlide("风险约束与稳健性", 10);
  addText(s, "约束诊断", 95, 145, 290, 48, 24, { bold: true, color: C.blue });
  addBullets(s, ["滚动 20 周实现跟踪误差", "行业主动权重与最大偏离", "周度换手率与优化状态"], 95, 210, 500, 20, 70);
  addText(s, "稳健性实验", 675, 145, 290, 48, 24, { bold: true, color: C.blue });
  addBullets(s, ["交易成本 10 / 20 / 30bp", "风险预算 4% / 5% / 6%", "因子剔除与无 BL 对照"], 675, 210, 500, 20, 70);
  addText(s, "正式回测后插入对比图表，并解释不利结果", 180, 545, 920, 58, 21, { fill: C.pale, align: "center", bold: true, color: C.navy });
}

// 11
{
  const s = baseSlide("结论 局限与成员分工", 11);
  addText(s, "结论", 90, 145, 170, 45, 24, { bold: true, color: C.blue });
  addText(s, "正式 Wind 结果完成后填写，不预设策略有效性", 90, 195, 500, 90, 21, { fill: C.pale });
  addText(s, "局限", 690, 145, 170, 45, 24, { bold: true, color: C.blue });
  addText(s, "指数历史长度、数据更新频率、成本假设与参数误差", 690, 195, 500, 90, 21, { fill: C.pale });
  addText(s, "成员分工", 90, 355, 200, 45, 24, { bold: true, color: C.blue });
  addText(s, "按成员列明 Wind 导出、数据清洗、因子、BL 优化、回测、报告与交叉核验", 90, 410, 1100, 90, 21, { fill: "#F4F7F9" });
  addText(s, "AI 使用说明：Codex 用于流程设计、代码框架和模板；小组成员核验全部数据、代码与结论", 90, 550, 1100, 58, 18, { color: C.gray, align: "center" });
}

const requirements = {
  explicitTotalSlideCount: 11,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  workspaceDir: ROOT,
};
const fontPolicy = { basis: "design", families: [FONT] };
const expectedSlideSizeEmu = "12192000,6858000";
const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
const stagingDir = path.join(ROOT, ".codex-finalizer");
await fs.mkdir(stagingDir, { recursive: true });
const candidatePath = path.join(stagingDir, "a500-candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
await finalizePresentation({
  ...requirements,
  candidatePath,
  finalPath: FINAL_PPTX,
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", expectedSlideSizeEmu, "--validate-heading-fit"],
  fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "a500-presentation.validation.json"),
});
console.log(FINAL_PPTX);
