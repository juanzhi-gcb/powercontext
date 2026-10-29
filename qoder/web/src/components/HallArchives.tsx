import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleDashed,
  CircleX,
  Code2,
  Database,
  FileText,
  LoaderCircle,
  PackageCheck,
  Play,
  X,
} from "lucide-react";
import { evaluatePublicAttempt, listPublicVerdicts } from "../publicEngine";
import type { AttemptInput, CheckResult, Evidence, Report } from "../types";
import { DecisionBadge } from "./DecisionBadge";
import { SourceTag, sourceMetaLead } from "./SourceTag";

export type HallSheetKind = "verdicts" | "project" | "precheck";

const repository = "https://github.com/juanzhi-gcb/powercontext/tree/submit/qoder/qoder";
const stanceLabels = { supports: "支持", refutes: "反证", limits: "限制" };
const verdicts = listPublicVerdicts();

const reasonTitles: Record<string, string> = {
  MECHANISM_REPACKAGED: "这可能是旧机制换了一种说法",
  DETERMINISTIC_GATE_FAILED: "最小实验的启动条件还不完整",
  NO_LOCATABLE_HISTORICAL_EVIDENCE: "现有证据不足以支持投入判断",
  DIFFERENTIATED_MECHANISM: "存在新的条件，但应先做最小判别实验",
  MECHANISM_RELATION_UNCERTAIN: "还不能确认它与历史机制的关系",
  COMPARISON_OUTPUT_INVALID: "比较结果未通过证据引用校验",
};

const reasonSummaries: Record<string, string> = {
  MECHANISM_REPACKAGED: "最接近的历史机制高度相似，而当前提案没有说明改变了什么关键条件。换新数据集、基准或术语，不能单独构成新的机制贡献。",
  DETERMINISTIC_GATE_FAILED: "数据、模型版本、算力、存储或首轮验证预算至少有一项未通过固定检查。先补齐条件，再决定是否继续。",
  NO_LOCATABLE_HISTORICAL_EVIDENCE: "没有找到足够且可定位的历史证据。先补充资料或缩小问题，再重新预检。",
  DIFFERENTIATED_MECHANISM: "当前提案声明了新的关键条件。不要直接扩大工程投入，先用最小实验排除最强竞争解释。",
  MECHANISM_RELATION_UNCERTAIN: "检索结果还不足以建立可靠的机制关系。补一段更具体的机制描述，或换一个可对照的近邻再查。",
  COMPARISON_OUTPUT_INVALID: "机制比较包含了无效或无法定位的引用。先修复引用，再重新预检。",
};

const checkLabels: Record<string, string> = {
  "engineering.data": "最小数据",
  "engineering.checkpoint": "模型版本",
  "engineering.gpu": "算力预算",
  "engineering.closed_loop": "首轮验证时间",
  "engineering.storage": "存储空间",
  "process.problem_first": "问题先于基线",
  "evidence.coverage": "证据可追溯",
  "evidence.discrimination": "竞争解释",
  "mechanism.repaint": "机制是否有新条件",
};

const checkDetails: Record<string, string> = {
  DATA_READY: "最小可用数据已经就绪。",
  DATA_NOT_READY: "先准备能够完成首轮验证的最小数据。",
  CHECKPOINT_READY: "所需模型和固定版本已经就绪。",
  CHECKPOINT_MISSING: "先固定所需模型及其版本，避免实验过程中发生变化。",
  GPU_BUDGET_OK: "可用 GPU 数量满足当前研究约束。",
  GPU_BUDGET_INSUFFICIENT: "可用 GPU 数量低于当前研究约束。",
  PILOT_WITHIN_BUDGET: "首轮验证时间没有超过预算。",
  PILOT_EXCEEDS_BUDGET: "首轮验证时间超过预算，请先缩小实验。",
  STORAGE_BUDGET_OK: "可用存储满足当前研究约束。",
  STORAGE_BUDGET_INSUFFICIENT: "可用存储低于当前研究约束。",
  PROBLEM_BEFORE_BASELINE: "已先声明研究问题，再选择比较基线。",
  BASELINE_BEFORE_PROBLEM: "不要先选基线，再反向包装成研究问题。",
  EVIDENCE_LOCATABLE: "关键历史比较都有可定位的原始证据。",
  EVIDENCE_MISSING: "至少一个关键历史比较缺少可定位证据。",
  COMPETING_EXPLANATION_DECLARED: "已声明需要排除的最强竞争解释。",
  COMPETING_EXPLANATION_MISSING: "补充一个可能解释同样结果的最强替代方案。",
  CHANGED_CONDITION_DECLARED: "已声明与历史机制不同的关键条件。",
  MECHANISM_REPACKAGED: "机制高度相似，但没有声明新的关键条件。",
};

interface PrecheckForm {
  title: string;
  idea: string;
  mechanism: string;
  differentiator: string;
  failure: string;
  competing: string;
  gpu: number;
  hours: number;
  dataReady: boolean;
  checkpointReady: boolean;
}

function dateOnly(value: string) {
  return value.slice(0, 10);
}

function seedTitle(seed: string) {
  const compact = seed.trim().replace(/\s+/g, " ");
  if (compact.length < 2) return "待命名考据";
  return compact.split(" ").slice(0, 8).join(" ").slice(0, 48);
}

function initialForm(seed: string): PrecheckForm {
  const idea = seed.trim();
  return {
    title: idea ? seedTitle(idea) : "",
    idea,
    mechanism: "",
    differentiator: "",
    failure: "如果核心机制在最小实验中不成立，或相对最强竞争解释没有可重复差异，则停止投入。",
    competing: "",
    gpu: 2,
    hours: 24,
    dataReady: true,
    checkpointReady: true,
  };
}

function comparisonDifference(value: string) {
  return value.startsWith("No changed causal condition was declared")
    ? "没有声明新的关键条件；应先把它们当作可能相同的机制，而不是用新术语覆盖旧结论。"
    : value;
}

function EvidenceRows({ evidence }: { evidence: Evidence[] }) {
  return <>{evidence.map((item) => <details className="hall-receipt-evidence" key={item.id}>
    <summary><FileText size={13} />{item.title}<small className="hall-evidence-date">{dateOnly(item.published_at)}</small><span className={`stance stance-${item.stance}`}>{stanceLabels[item.stance]}</span><ChevronRight size={13} /></summary>
    <blockquote>{item.excerpt}</blockquote>
    {/^https?:\/\//.test(item.locator) ? <a href={item.locator} target="_blank" rel="noreferrer">{item.locator}<ArrowUpRight size={12} /></a> : <code>{item.locator}</code>}
  </details>)}</>;
}

function HallSheet({
  kicker,
  title,
  serial,
  onClose,
  footer,
  children,
}: {
  kicker: string;
  title: string;
  serial: string;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return <div className="hall-sheet-wrap" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <article className="hall-receipt hall-sheet" role="dialog" aria-modal="true" aria-labelledby="hall-sheet-title">
      <button ref={closeRef} className="hall-receipt-close" onClick={onClose} aria-label={`收起${title}`}><X size={17} /></button>
      <header className="hall-receipt-head">
        <div><span>{kicker}</span><strong id="hall-sheet-title">{title}</strong></div>
        <em>{serial}</em>
      </header>
      {children}
      {footer && <footer className="hall-receipt-foot">{footer}</footer>}
    </article>
  </div>;
}

function VerdictSheet({ onClose, onSearch, onSearchWith }: { onClose: () => void; onSearch: () => void; onSearchWith: (query: string) => void }) {
  return <HallSheet
    kicker="ARCHIVE VERDICTS / 历史裁决"
    title="取回旧裁决"
    serial={`VERDICT ${String(verdicts.length).padStart(2, "0")}`}
    onClose={onClose}
    footer={<div className="hall-sheet-actions">
      <button className="hall-brass-btn" onClick={onSearch}>再查一张<ArrowRight size={14} /></button>
    </div>}
  >
    <div className="hall-case-list">
      {verdicts.map((verdict, index) => <details className="hall-case" key={verdict.id} open={index === 0}>
        <summary>
          <span className="hall-sheet-index">{String(index + 1).padStart(2, "0")}</span>
          <div>
            <div className="hall-sheet-title"><h3>{verdict.title}</h3><DecisionBadge decision={verdict.decision} /></div>
            <div className="hall-sheet-meta">{verdict.task}，{dateOnly(verdict.available_at)}，{verdict.evidence.length} 条证据</div>
          </div>
          <ChevronRight size={14} />
        </summary>
        <div className="hall-case-body">
          <p className="hall-case-mechanism">{verdict.mechanism}</p>
          <p className="hall-case-stop"><strong>当时写下的停止条件</strong>{verdict.failure_condition}</p>
          <EvidenceRows evidence={verdict.evidence} />
          <div className="hall-case-actions">
            <button className="hall-paper-btn" onClick={() => onSearchWith(`${verdict.title} ${verdict.mechanism}`)}>拿它去查重<ArrowRight size={13} /></button>
          </div>
        </div>
      </details>)}
    </div>
  </HallSheet>;
}

function ProjectSheet({ onClose, onSearch }: { onClose: () => void; onSearch: () => void }) {
  return <HallSheet
    kicker="SYSTEM / 技术档案"
    title="技术档案"
    serial="BUILD / QODER × OCEANBASE"
    onClose={onClose}
    footer={<div className="hall-sheet-actions">
      <button className="hall-paper-btn" onClick={onSearch}>回值班台</button>
      <a className="hall-brass-btn" href={repository} target="_blank" rel="noreferrer">代码仓库<ArrowUpRight size={13} /></a>
    </div>}
  >
    <div className="hall-tech-grid">
      <div><Database size={22} /><h3>seekdb / 研究事实源</h3><p>保存资料原文、日期、稳定 locator 与证据；执行向量距离、全文相关性和任务、状态、时间过滤。</p></div>
      <div><PackageCheck size={22} /><h3>PowerContext / 连续工作台</h3><p>保存研究约束、活跃指针与人工接受的知识线。运行只记录 Artifact ID、revision 与 hash，回放读取精确修订。</p></div>
      <div><Code2 size={22} /><h3>Qoder / 开发与交付</h3><p>需求拆解、FastAPI 与 React 实现、调试、回归验证和 Qoder Sites 发布均保留开发记录。</p></div>
    </div>
    <h3 className="hall-sheet-subhead">本地完整链路</h3>
    <pre className="hall-sheet-code"><code>{`cd qoder
docker compose -f deploy/compose.yaml up --build

# 打开 http://127.0.0.1:5173
# 独立验证 profile
docker compose -f deploy/compose.yaml --profile validation up -d --build validation-api
cd server
uv sync --extra dev
uv run pytest
uv run python ../evaluation/run_golden.py`}</code></pre>
  </HallSheet>;
}

function ReportSheet({ report, onBack, onClose, onSearch }: { report: Report; onBack: () => void; onClose: () => void; onSearch: () => void }) {
  const pass = report.checks.filter((item) => item.status === "pass").length;
  const fail = report.checks.filter((item) => item.status === "fail").length;
  const warn = report.checks.filter((item) => item.status === "warn" || item.status === "unknown").length;
  const experiments: Array<[string, string]> = [
    ["判别假设", report.minimal_experiment.hypothesis],
    ["唯一干预", report.minimal_experiment.intervention],
    ["最强控制", report.minimal_experiment.control],
    ["预注册指标", report.minimal_experiment.metric],
    ["通过阈值", report.minimal_experiment.threshold],
    ["停止条件", report.minimal_experiment.stop_condition],
  ];

  useEffect(() => {
    document.querySelector<HTMLElement>(".hall-sheet")?.scrollTo({ top: 0 });
  }, [report]);

  return <HallSheet
    kicker="PUBLIC PRECHECK / 浏览器内计算"
    title={report.attempt.title}
    serial={`CASE ${report.id}`}
    onClose={onClose}
    footer={<div className="hall-sheet-actions">
      <button className="hall-paper-btn" onClick={onBack}>改一改再算</button>
      <button className="hall-brass-btn" onClick={onSearch}>再查一张<ArrowRight size={14} /></button>
    </div>}
  >
    <div className="hall-verdict">
      <div>
        <span className="hall-sheet-kicker">MACHINE DECISION / {report.reason_code}</span>
        <h3>{reasonTitles[report.reason_code] ?? report.reason_code}</h3>
        <p>{reasonSummaries[report.reason_code] ?? report.summary}</p>
      </div>
      <div className="hall-verdict-side">
        <DecisionBadge decision={report.machine_decision} large />
        <span className="hall-verdict-code">{report.machine_decision}</span>
      </div>
    </div>
    <div className="hall-sheet-ledger is-four">
      <div><strong>{pass}</strong><span>项通过</span></div>
      <div><strong>{fail}</strong><span>项失败</span></div>
      <div><strong>{report.evidence_ids.length}</strong><span>条引用证据</span></div>
      <div><strong>{report.comparisons.length}</strong><span>条历史比较</span></div>
    </div>

    <section className="hall-report-section">
      <div className="hall-report-head"><span>01</span><h3>过去最接近的尝试</h3><em>{report.comparisons.length} 条</em></div>
      {report.comparisons.length > 0 ? <ol className="hall-sheet-list">
        {report.comparisons.map((comparison, index) => <li key={comparison.attempt_id}>
          <span className="hall-sheet-index">{String(index + 1).padStart(2, "0")}</span>
          <div className="hall-sheet-body">
            <div className="hall-sheet-title"><h3>{comparison.title}</h3>{comparison.historical_decision && <DecisionBadge decision={comparison.historical_decision} />}</div>
            <div className="hall-sheet-meta"><SourceTag source={comparison.source} recordType={comparison.record_type} url={comparison.source_url} />{sourceMetaLead(comparison.source, comparison.record_type, comparison.outcome, comparison.task)}，{dateOnly(comparison.available_at)}，机制相似度 {comparison.mechanism_similarity.toFixed(2)}，{comparison.evidence.length} 条证据</div>
            <p className="hall-compare-diff">{comparisonDifference(comparison.mechanism_difference)}</p>
            <EvidenceRows evidence={comparison.evidence} />
          </div>
        </li>)}
      </ol> : <div className="hall-report-empty">没有召回可定位的历史比较。补一段更具体的机制描述，或先把相关资料收进馆藏。</div>}
    </section>

    <details className="hall-report-checks">
      <summary><span>02</span><strong>检查依据</strong><em>{pass} 通过 / {fail} 失败 / {warn} 提示</em><ChevronRight size={14} /></summary>
      <ul>
        {report.checks.map((item: CheckResult) => <li key={item.name}>
          {item.status === "pass" ? <Check className="check-pass" size={14} /> : item.status === "fail" ? <CircleX className="check-fail" size={14} /> : <CircleDashed className="check-warn" size={14} />}
          <div>
            <strong>{checkLabels[item.name] ?? item.name}</strong><small>{item.reason_code}</small>
            <p>{checkDetails[item.reason_code] ?? item.detail}</p>
          </div>
        </li>)}
      </ul>
    </details>

    <section className="hall-report-section">
      <div className="hall-report-head"><span>03</span><h3>最小判别实验</h3><em>先做这一步</em></div>
      <dl className="hall-experiment">
        {experiments.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
    </section>

    <p className="hall-report-trace">规则 {report.versions.rules}，比较器 {report.versions.model}，嵌入 {report.versions.embedding}，快照 {report.snapshot_hash?.slice(0, 12) ?? "—"}…</p>
  </HallSheet>;
}

function PrecheckSheet({ seed, onClose, onSearchWith }: { seed: string; onClose: () => void; onSearchWith: (query: string) => void }) {
  const [form, setForm] = useState<PrecheckForm>(() => initialForm(seed));
  const [report, setReport] = useState<Report | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  function set<K extends keyof PrecheckForm>(key: K, value: PrecheckForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const input: AttemptInput = {
        title: form.title.trim(),
        idea: form.idea.trim(),
        mechanism: form.mechanism.trim(),
        task: "general",
        domain: "",
        failure_condition: form.failure.trim(),
        assumptions: [],
        competing_explanations: form.competing.split(/[；;]/).map((item) => item.trim()).filter(Boolean),
        differentiator: form.differentiator.trim(),
        available_at: new Date().toISOString(),
        gpu_count: form.gpu,
        data_ready: form.dataReady,
        checkpoint_ready: form.checkpointReady,
        pilot_hours: form.hours,
        storage_gb: 100,
        baseline_first: false,
      };
      setReport(await evaluatePublicAttempt(input, { matchAll: true }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预检失败，请稍后再试。");
    } finally {
      setPending(false);
    }
  }

  if (report) return <ReportSheet report={report} onBack={() => setReport(null)} onClose={onClose} onSearch={() => onSearchWith(report.attempt.idea)} />;

  return <HallSheet
    kicker="PUBLIC PRECHECK / 浏览器内计算"
    title="正式考据"
    serial={seed ? "FROM RECEIPT" : "NEW CASE"}
    onClose={onClose}
    footer={<div className="hall-sheet-actions">
      <button type="submit" form="hall-precheck-form" className="hall-brass-btn" disabled={pending}>
        {pending ? <LoaderCircle className="spin" size={15} /> : <Play size={14} />}{pending ? "正在翻档" : "生成避坑报告"}
      </button>
    </div>}
  >
    <form className="hall-form" id="hall-precheck-form" onSubmit={submit}>
      <label className="hall-field"><span>给它一个名字</span><input required minLength={2} value={form.title} onChange={(event) => set("title", event.target.value)} placeholder="例如：限制观察统计量的可识别性实验" /></label>
      <label className="hall-field"><span>你想研究什么？</span><textarea required minLength={10} rows={3} value={form.idea} onChange={(event) => set("idea", event.target.value)} placeholder="用自然语言描述问题和准备尝试的路线" /></label>
      <label className="hall-field"><span>你认为它为什么可能有效？</span><textarea required minLength={10} rows={4} value={form.mechanism} onChange={(event) => set("mechanism", event.target.value)} placeholder="写下起作用的机制，而不只是准备使用的方法名称" /></label>
      <label className="hall-field"><span>和过去相比，你改变了什么？</span><textarea rows={3} value={form.differentiator} onChange={(event) => set("differentiator", event.target.value)} placeholder="留空时，若最接近的历史机制高度相似，会被判为“换皮”。" /></label>
      <label className="hall-field"><span>出现什么结果就应该停止？</span><textarea required rows={2} value={form.failure} onChange={(event) => set("failure", event.target.value)} /></label>
      <label className="hall-field"><span>最强竞争解释（可留空）</span><input value={form.competing} onChange={(event) => set("competing", event.target.value)} placeholder="例如：简单加权基线也能解释同样的结果" /></label>
      <div className="hall-form-row">
        <label className="hall-field"><span>可用 GPU 数量</span><input type="number" min={0} value={form.gpu} onChange={(event) => set("gpu", Number(event.target.value))} /></label>
        <label className="hall-field"><span>首轮验证需要几小时？</span><input type="number" min={1} value={form.hours} onChange={(event) => set("hours", Number(event.target.value))} /></label>
      </div>
      <div className="hall-form-toggles">
        <label className="hall-toggle"><input type="checkbox" checked={form.dataReady} onChange={(event) => set("dataReady", event.target.checked)} />最小数据已经就绪</label>
        <label className="hall-toggle"><input type="checkbox" checked={form.checkpointReady} onChange={(event) => set("checkpointReady", event.target.checked)} />模型版本已经固定</label>
      </div>
      {error && <p className="hall-form-error" role="alert">{error}</p>}
    </form>
  </HallSheet>;
}

export function HallArchivesSheet({
  kind,
  seed,
  onClose,
  onSearch,
  onSearchWith,
}: {
  kind: HallSheetKind;
  seed: string;
  onClose: () => void;
  onSearch: () => void;
  onSearchWith: (query: string) => void;
}) {
  if (kind === "verdicts") return <VerdictSheet onClose={onClose} onSearch={onSearch} onSearchWith={onSearchWith} />;
  if (kind === "project") return <ProjectSheet onClose={onClose} onSearch={onSearch} />;
  return <PrecheckSheet seed={seed} onClose={onClose} onSearchWith={onSearchWith} />;
}
