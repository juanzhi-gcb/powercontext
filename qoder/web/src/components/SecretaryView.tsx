import { useEffect, useState } from "react";
import {
  Brain,
  Check,
  CircleDashed,
  Clock3,
  Copy,
  FileText,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, staticDemo } from "../api";
import { sampleSecretary } from "../sample";
import type { SecretaryProposal, SecretaryProposalKind, SecretaryReport, SecretaryReviewStatus } from "../types";

const kindMeta: Record<SecretaryProposalKind, { label: string; hint: string; icon: typeof GitBranch }> = {
  knowledge_line: { label: "知识线", hint: "多份资料指向相近主题", icon: GitBranch },
  near_duplicate: { label: "可能重复", hint: "表述高度接近，可能放大同一证据", icon: Copy },
  orphan: { label: "孤立资料", hint: "暂未连接到其他资料", icon: CircleDashed },
};

const statusMeta: Record<SecretaryReviewStatus, { label: string; tone: string }> = {
  proposed: { label: "待审阅", tone: "proposed" },
  accepted: { label: "已接受", tone: "accepted" },
  rejected: { label: "已拒绝", tone: "rejected" },
  snoozed: { label: "已暂缓", tone: "snoozed" },
};

function errorText(reason: unknown) {
  const message = reason instanceof Error ? reason.message : "秘书运行失败";
  if (message.includes("PowerContext")) return "研究秘书需要 PowerContext 保存提案与审阅状态。请先在「项目与复现」中检查本地服务。";
  return message;
}

function ReviewControls({ proposal, pending, readOnly, onReview }: {
  proposal: SecretaryProposal;
  pending: boolean;
  readOnly: boolean;
  onReview: (status: SecretaryReviewStatus, note: string) => void;
}) {
  const [note, setNote] = useState(proposal.review_note);
  const [open, setOpen] = useState(proposal.status === "proposed");

  useEffect(() => {
    setNote(proposal.review_note);
    setOpen(proposal.status === "proposed");
  }, [proposal.status, proposal.review_note]);

  if (readOnly) {
    return <div className="secretary-review-summary">
      <LockKeyhole size={14} />
      <span>{proposal.status === "proposed" ? "公开演示不可审阅；启动本地服务后可接受、暂缓或拒绝。" : "已记录审阅结果"}</span>
      {proposal.review_note && <q>{proposal.review_note}</q>}
    </div>;
  }

  if (!open) {
    return <div className="secretary-review-summary"><Check size={14} /><span>已记录审阅结果</span>{proposal.review_note && <q>{proposal.review_note}</q>}<button type="button" className="text-button" onClick={() => setOpen(true)}>修改审阅</button></div>;
  }

  return (
    <div className="secretary-review">
      <label>审阅备注（可选）
        <input value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} placeholder="例如：这只是主题相近，暂不作为同一机制。" />
      </label>
      <div className="secretary-review-actions">
        <button type="button" className="button button-accent" disabled={pending || proposal.status === "accepted"} onClick={() => onReview("accepted", note)}><Check size={15} />接受并写入记忆</button>
        <button type="button" className="button button-secondary" disabled={pending || proposal.status === "snoozed"} onClick={() => onReview("snoozed", note)}><Clock3 size={15} />暂缓</button>
        <button type="button" className="button button-quiet" disabled={pending || proposal.status === "rejected"} onClick={() => onReview("rejected", note)}><X size={15} />拒绝</button>
        {proposal.status !== "proposed" && <button type="button" className="text-button" onClick={() => setOpen(false)}>收起</button>}
      </div>
      <p className="secretary-review-note">接受只会把这条归纳写入 PowerContext，不会修改证据、预检结论或人工终审。</p>
    </div>
  );
}

export function SecretaryView({ live, onSources }: { live: boolean; onSources: () => void }) {
  const [report, setReport] = useState<SecretaryReport | null>(staticDemo ? sampleSecretary : null);
  const [loading, setLoading] = useState(!staticDemo && live);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (staticDemo || !live) return;
    let active = true;
    setLoading(true);
    api.getSecretary().then((value) => {
      if (active) setReport(value);
    }).catch((reason) => {
      if (active) setError(errorText(reason));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [live]);

  async function run() {
    setPending("run");
    setError("");
    try {
      setReport(await api.runSecretary());
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setPending("");
    }
  }

  async function review(proposalId: string, status: SecretaryReviewStatus, note: string) {
    setPending(proposalId);
    setError("");
    try {
      setReport(await api.reviewSecretary(proposalId, status, note));
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setPending("");
    }
  }

  const readyReport = report?.status === "ready" ? report : null;
  const proposals = readyReport?.proposals ?? [];
  const controlsDisabled = !live || Boolean(pending) || staticDemo;

  return (
    <div className="page secretary-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">RESEARCH SECRETARY / PROPOSALS ONLY</span>
          <h1>让资料形成知识线，但由你决定哪条成立。</h1>
          <p>研究秘书扫描本地资料库，用词面重叠与向量相似度提出知识线、疑似重复和孤立资料。它只生成可追溯提案，不修改证据、预检结论或人工裁决。</p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" onClick={onSources}>管理资料库</button>
          <button className="button button-dark" onClick={run} disabled={controlsDisabled}>
            {pending === "run" ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
            {pending === "run" ? "正在梳理资料" : readyReport ? "重新扫描资料" : "运行秘书扫描"}
          </button>
        </div>
      </div>

      {!live && <div className="notice notice-demo"><LockKeyhole size={18} /><div><strong>{staticDemo ? "公开网站展示固定的秘书提案样例" : "本地研究服务尚未连接"}</strong><p>{staticDemo ? "下面的知识线、审阅状态与 PowerContext 修订均为静态示例，不会根据你的操作真实运行。启动本地服务后，才会扫描你自己的 seekdb 资料。" : "研究秘书会读写本地 seekdb 与 PowerContext。请先在「项目与复现」启动服务。"}</p></div></div>}
      {error && <div className="notice notice-error" role="alert">{error}</div>}

      {loading && <div className="secretary-loading"><LoaderCircle className="spin" size={20} />正在读取上一次秘书工作区…</div>}

      {!loading && report?.status === "not_run" && <section className="secretary-empty">
        <SparkEmpty />
        <h2>还没有运行过研究秘书</h2>
        <p>先导入自己的论文笔记、复现记录或技术报告，再让秘书生成第一版知识线提案。没有提案时会如实显示为空，不会编造资料。</p>
        <button className="button button-dark" onClick={run} disabled={!live || Boolean(pending)}><GitBranch size={16} />生成第一版提案</button>
      </section>}

      {readyReport && <section className="secretary-overview">
        <div className="secretary-stat"><span>已连接资料</span><strong>{readyReport.source_count}</strong><small>个分段进入扫描</small></div>
        <div className="secretary-stat"><span>本次新增</span><strong>{readyReport.new_source_count}</strong><small>{readyReport.new_source_count ? "上次运行后导入" : "没有新资料"}</small></div>
        <div className="secretary-stat"><span>已接受知识线</span><strong>{readyReport.accepted_count}</strong><small>写入 PowerContext</small></div>
        <div className="secretary-stat"><span>提案总数</span><strong>{proposals.length}</strong><small>由人工逐条审阅</small></div>
      </section>}

      {readyReport && <section className="secretary-artifacts">
        <div className="secretary-artifact"><Brain size={18} /><div><span>SECRETARY WORKSPACE</span><strong>运行状态与审阅收件箱</strong><code>revision {readyReport.workspace?.revision ?? "—"}，{readyReport.run_id ?? "—"}</code></div></div>
        <div className="secretary-artifact"><ShieldCheck size={18} /><div><span>ACCEPTED CONTEXT</span><strong>已接受知识线进入预检上下文</strong><code>revision {readyReport.context?.revision ?? "—"}，{readyReport.context?.artifact_id ?? "—"}</code></div></div>
        <div className="secretary-artifact-note"><Clock3 size={15} /><span>运行于 {readyReport.generated_at ? new Date(readyReport.generated_at).toLocaleString("zh-CN", { hour12: false }) : "—"}。稳定提案 ID 会保留已有审阅结果。</span></div>
      </section>}

      {readyReport && <div className="secretary-inbox">
        <div className="secretary-inbox-heading"><div><span className="section-kicker">REVIEW INBOX</span><h2>{proposals.length ? `${proposals.length} 条待你判断的提案` : "本次没有生成提案"}</h2></div><span className="demo-chip">{staticDemo ? "静态样例" : "机器提案，人工审阅"}</span></div>
        {!proposals.length && <div className="empty-state">资料太少或尚未形成可解释的连接。再导入一份相关资料后会重新计算；秘书不会为了凑数而虚构知识线。</div>}
        <div className="secretary-proposal-list">
          {proposals.map((proposal) => {
            const kind = kindMeta[proposal.kind];
            const status = statusMeta[proposal.status];
            const Icon = kind.icon;
            return <article className={`secretary-proposal status-${status.tone}`} key={proposal.id}>
              <header className="secretary-proposal-heading">
                <div className="secretary-kind"><Icon size={16} /><span>{kind.label}</span><small>{kind.hint}</small></div>
                <div className="secretary-proposal-badges">
                  {proposal.kind !== "orphan" && <span className="secretary-confidence">连接强度 {proposal.confidence.toFixed(2)}</span>}
                  <span className={`secretary-status status-${status.tone}`}>{status.label}</span>
                </div>
              </header>
              <h3>{proposal.title}</h3>
              <p className="secretary-summary">{proposal.summary}</p>
              <div className="secretary-sources">
                {proposal.sources.map((source) => <div className="secretary-source" key={source.attempt_id}>
                  <FileText size={15} />
                  <div><strong>{source.title}</strong>{/^https?:\/\//.test(source.locator) ? <a href={source.locator} target="_blank" rel="noreferrer">{source.locator}</a> : <code>{source.locator}</code>}</div>
                  <span>{source.evidence_ids.length} 条证据，{source.published_at.slice(0, 10)}</span>
                </div>)}
              </div>
              <div className="secretary-next"><span>建议下一步</span><p>{proposal.next_action}</p></div>
              <ReviewControls proposal={proposal} pending={pending === proposal.id || Boolean(pending && pending !== "run")} readOnly={staticDemo || !live} onReview={(nextStatus, note) => review(proposal.id, nextStatus, note)} />
            </article>;
          })}
        </div>
      </div>}

      <section className="secretary-boundary">
        <Brain size={22} />
        <div>
          <span className="section-kicker">WHY POWERCONTEXT</span>
          <h2>秘书的记忆，不是研究事实的另一份副本</h2>
          <p>运行状态、提案和人工审阅保存在 PowerContext。只有你接受的知识线会以独立 artifact 进入后续预检的上下文引用；原始证据、裁决与机器建议仍以 seekdb 为唯一事实源。秘书运行失败时，不会静默改写任何研究结论。</p>
        </div>
      </section>
    </div>
  );
}

function SparkEmpty() {
  return <div className="secretary-empty-mark" aria-hidden="true"><GitBranch size={26} /><span /><span /></div>;
}
