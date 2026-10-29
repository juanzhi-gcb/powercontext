import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronRight,
  FileClock,
  FlaskConical,
  GitBranch,
  Layers3,
  LibraryBig,
  LoaderCircle,
  NotebookPen,
  Plus,
  RotateCcw,
  Search,
  X,
} from "lucide-react";
import { api, staticDemo } from "./api";
import { sampleHealth, sampleReport } from "./sample";
import type { Decision, Health, Page, Report } from "./types";
import { ReportView } from "./components/ReportView";
import { NewPrecheck } from "./components/NewPrecheck";
import { EvidenceView } from "./components/EvidenceView";
import { RegressionView } from "./components/RegressionView";
import { ContextView } from "./components/ContextView";
import { ProjectView } from "./components/ProjectView";
import { ArchiveHall } from "./components/ArchiveHall";
import { SourcesView } from "./components/SourcesView";
import { SecretaryView } from "./components/SecretaryView";

const navigation = [
  { id: "hall" as const, label: "档案馆大厅", icon: Search, group: "开始使用" },
  { id: "sources" as const, label: "研究资料库", icon: LibraryBig, group: "开始使用" },
  { id: "new" as const, label: "完整预检", icon: Plus, group: "开始使用" },
  { id: "report" as const, label: "预检报告", icon: Activity, group: "开始使用" },
  { id: "secretary" as const, label: "研究秘书", icon: NotebookPen, group: "高级功能" },
  { id: "evidence" as const, label: "证据出处", icon: Layers3, group: "高级功能" },
  { id: "regression" as const, label: "历史回放", icon: RotateCcw, group: "高级功能" },
  { id: "context" as const, label: "记忆与状态", icon: Brain, group: "高级功能" },
  { id: "project" as const, label: "项目与复现", icon: BookOpen, group: "交付" },
];

function BrandMark() {
  return <svg viewBox="0 0 38 38" aria-hidden="true"><path d="M5 30V8l14 14L33 8v22" /><path d="M5 30h28" /><circle cx="19" cy="22" r="3" /></svg>;
}

function DecisionDialog({ report, onClose, onSaved }: { report: Report; onClose: () => void; onSaved: (contextWarning?: string | null) => void }) {
  const [decision, setDecision] = useState<Decision>(report.machine_decision);
  const [reason, setReason] = useState("");
  const [restart, setRestart] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const saved = await api.decide(report.id, decision, reason, restart);
      onSaved(saved.context_warning);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "终审保存失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="decision-title">
        <div className="dialog-heading"><div><span className="section-kicker">HUMAN REVIEW</span><h2 id="decision-title">保存独立的人工终审</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={19} /></button></div>
        <p>机器建议保持不可变；人工可以覆盖，但必须留下理由与重启条件。</p>
        <form onSubmit={submit}>
          <label>最终裁决<select value={decision} onChange={(event) => setDecision(event.target.value as Decision)}><option value="GO">GO</option><option value="NO_GO">NO_GO</option><option value="CONDITIONAL_GO">CONDITIONAL_GO</option><option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE</option></select></label>
          <label>终审理由<textarea required minLength={5} rows={4} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="说明接受或覆盖机器建议的依据" /></label>
          <label>重启条件<textarea rows={3} value={restart} onChange={(event) => setRestart(event.target.value)} placeholder="什么新证据或环境变化可以重新打开此路线？" /></label>
          {error && <div className="notice notice-error">{error}</div>}
          <div className="dialog-actions"><button type="button" className="button button-secondary" onClick={onClose}>取消</button><button className="button button-dark" disabled={pending}>{pending ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}提交到 seekdb</button></div>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("hall");
  const [draft, setDraft] = useState("");
  const [report, setReport] = useState<Report>(sampleReport);
  const [sample, setSample] = useState(true);
  const [health, setHealth] = useState<Health>(sampleHealth);
  const [live, setLive] = useState(false);
  const [checking, setChecking] = useState(!staticDemo);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (staticDemo) return;
    api.health().then((value) => {
      setHealth(value);
      setLive(value.seekdb.status === "ready");
    }).catch(() => setLive(false)).finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    const navigate = (event: Event) => setPage((event as CustomEvent<Page>).detail);
    document.addEventListener("nullpath:navigate", navigate);
    return () => document.removeEventListener("nullpath:navigate", navigate);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function showReport(value: Report) {
    setReport(value);
    setSample(false);
    setPage("report");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const isDemo = staticDemo || !live || sample;
  const inHall = page === "hall";
  const groups = ["开始使用", "高级功能", "交付"];

  return (
    <div className={`app-shell${inHall ? " hall-mode" : ""}`}>
      <aside className="sidebar">
        <button className="brand" onClick={() => setPage("hall")} aria-label="NullPath 首页"><BrandMark /><span><strong>NullPath</strong><small>RESEARCH CI</small></span></button>
        <nav className="main-nav" aria-label="主导航">
          {groups.map((group) => <div className="nav-group" key={group}><span className="nav-group-label">{group}</span>{navigation.filter((item) => item.group === group).map((item) => <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => setPage(item.id)}><item.icon size={17} strokeWidth={1.7} /><span>{item.label}</span>{page === item.id && <ChevronRight size={14} />}</button>)}</div>)}
        </nav>
        <div className="sidebar-bottom">
          <button className="service-card" onClick={() => setPage("context")}>
            <span className={`pulse-dot ${live ? "online" : staticDemo ? "demo" : "offline"}`} />
            <div><strong>{checking ? "检查本地服务" : live ? "本地服务已连接" : staticDemo ? "公开版，实时计算" : "未连接本地服务"}</strong><small>{live ? "seekdb / PowerContext" : staticDemo ? "公开馆藏，结果不落盘" : "查看技术分工与状态"}</small></div>
            <ChevronRight size={14} />
          </button>
          <div className="competition-mark"><FlaskConical size={15} /><span>Qoder × OceanBase<br />2026 Competition</span></div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><button className="breadcrumb-home" onClick={() => setPage("hall")}>档案馆大厅</button><ChevronRight size={13} /><strong>{navigation.find((item) => item.id === page)?.label}</strong></div>
          <div className="topbar-actions">
            {staticDemo ? <span className="demo-notice"><FileClock size={14} />公开版，浏览器内计算</span> : !live && <span className="demo-notice"><FileClock size={14} />展示数据已标注</span>}
            {live && <span className="live-notice"><span className="pulse-dot online" />LIVE</span>}
            <a href="https://github.com/juanzhi-gcb/powercontext/tree/submit/qoder/qoder" target="_blank" rel="noreferrer" aria-label="打开代码仓库"><GitBranch size={17} /><span>Repository</span><ArrowUpRight size={13} /></a>
          </div>
        </header>
        <main>
          {page === "hall" && <ArchiveHall live={live} onContinue={(idea) => { setDraft(idea); setPage("new"); }} onNavigate={setPage} />}
          {page === "sources" && <SourcesView live={live} onSearch={() => setPage("hall")} onSecretary={() => setPage("secretary")} />}
          {page === "secretary" && <SecretaryView live={live} onSources={() => setPage("sources")} />}
          {page === "report" && <ReportView report={report} isDemo={isDemo} publicComputed={staticDemo && !sample} onEvidence={() => setPage("evidence")} onDecision={() => setDecisionOpen(true)} />}
          {page === "new" && <NewPrecheck disabled={!live} draft={draft} onComplete={showReport} />}
          {page === "evidence" && <EvidenceView report={report} isDemo={isDemo} />}
          {page === "regression" && <RegressionView disabled={!live} onComplete={showReport} />}
          {page === "context" && <ContextView health={staticDemo ? sampleHealth : health} isDemo={staticDemo} />}
          {page === "project" && <ProjectView />}
        </main>
      </div>
      {decisionOpen && <DecisionDialog report={report} onClose={() => setDecisionOpen(false)} onSaved={(contextWarning) => { setToast(contextWarning ? `人工终审已保存到 seekdb，但 PowerContext 更新失败：${contextWarning}` : "人工终审已保存到 seekdb，PowerContext 活跃指针已按顺序更新"); api.health().then(setHealth).catch(() => undefined); }} />}
      {toast && <div className="toast" role="status"><CheckCircle2 size={17} />{toast}<button onClick={() => setToast("")} aria-label="关闭通知"><X size={15} /></button></div>}
    </div>
  );
}
