import { ArrowDown, ArrowRight, FileSearch, FileText, GitCompareArrows, Quote } from "lucide-react";
import type { Report } from "../types";
import { DecisionBadge } from "./DecisionBadge";

export function EvidenceView({ report, isDemo }: { report: Report; isDemo: boolean }) {
  return (
    <div className="page evidence-page">
      <div className="page-heading">
        <div><span className="eyebrow">TRACE / EVIDENCE LINEAGE</span><h1>从裁决逐层回到原始出处</h1><p>每条关键比较都保留检索分数、机制差异、证据 ID、原文定位与可用时间。</p></div>
        {isDemo && <span className="demo-chip">公开馆藏证据，不是原始实验日志</span>}
      </div>
      <section className="lineage-root">
        <span className="lineage-step">DECISION</span>
        <DecisionBadge decision={report.machine_decision} large />
        <div><strong>{report.reason_code}</strong><p>{report.summary}</p></div>
        <span className="lineage-arrow"><ArrowDown size={20} /></span>
      </section>
      <div className="evidence-columns">
        {report.comparisons.map((comparison) => (
          <section className="lineage-branch" key={comparison.attempt_id}>
            <div className="lineage-comparison">
              <div className="lineage-node-title"><GitCompareArrows size={18} /><span>COMPARISON</span></div>
              <h2>{comparison.title}</h2>
              <p>{comparison.mechanism_difference}</p>
              <div className="lineage-scores"><span>similarity {comparison.mechanism_similarity.toFixed(2)}</span><span>RRF {comparison.fused_score.toFixed(5)}</span></div>
            </div>
            <div className="branch-connector"><ArrowDown size={18} /></div>
            <div className="evidence-stack">
              {comparison.evidence.length === 0 && <div className="empty-state">该比较缺少 cutoff 前证据，不能支撑实质裁决。</div>}
              {comparison.evidence.map((evidence) => (
                <article className="evidence-card" key={evidence.id}>
                  <div className="evidence-card-top"><span className={`stance stance-${evidence.stance}`}>{evidence.stance}</span><span>{evidence.source_type}</span></div>
                  <h3><FileText size={17} />{evidence.title}</h3>
                  <blockquote><Quote size={17} />{evidence.excerpt}</blockquote>
                  <div className="evidence-locator"><FileSearch size={15} /><code>{evidence.locator}</code></div>
                  <footer><span>ID {evidence.id}</span><time>{evidence.published_at.slice(0, 10)}</time></footer>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
      <section className="integrity-panel">
        <div><span className="section-kicker">INTEGRITY</span><h2>时间边界与版本</h2></div>
        <div className="integrity-grid">
          <div><span>统一截止时间</span><strong>{report.cutoff.slice(0, 10)}</strong></div>
          <div><span>检索快照</span><strong>{report.snapshot_hash?.slice(0, 16) ?? "—"}</strong></div>
          <div><span>上下文修订</span><strong>{report.context_refs.map((ref) => `${ref.kind}@${ref.revision}`).join(", ") || "—"}</strong></div>
        </div>
        <p>回放只断言裁决、原因、证据召回与硬门槛；不要求模型文案或完整向量排序逐字一致。</p>
        <a href="#project" onClick={(event) => { event.preventDefault(); document.dispatchEvent(new CustomEvent("nullpath:navigate", { detail: "project" })); }}>查看复现步骤 <ArrowRight size={14} /></a>
      </section>
    </div>
  );
}
