import { useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  CircleDashed,
  Clock3,
  Database,
  FlaskConical,
  GitCompareArrows,
  UserCheck,
  X,
} from "lucide-react";
import type { Report } from "../types";
import { DecisionBadge } from "./DecisionBadge";

const checkIcons = {
  pass: Check,
  fail: X,
  warn: CircleDashed,
  unknown: CircleDashed,
};

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
  DETERMINISTIC_GATE_FAILED: "数据、模型版本、算力、存储或首轮验证预算至少有一项未通过固定检查。先补齐下面标出的条件，再决定是否继续。",
  NO_LOCATABLE_HISTORICAL_EVIDENCE: "没有找到足够且可定位的历史证据。先补充资料或缩小问题，再重新预检。",
  DIFFERENTIATED_MECHANISM: "当前提案声明了新的关键条件。不要直接扩大工程投入，先用下面的最小实验排除最强竞争解释。",
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
  "context.restore": "研究记忆恢复",
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
  CONTEXT_UNAVAILABLE: "PowerContext 暂时不可用；请检查上下文警告。",
};

const regressionLabels: Record<string, string> = {
  decision: "机器建议一致",
  required_evidence: "必需证据已召回",
  forbidden_evidence: "禁止证据未泄漏",
  cutoff_integrity: "时间截断完整",
  snapshot_integrity: "事实快照一致",
  version_integrity: "规则与模型版本一致",
  context_integrity: "上下文修订一致",
};

function number(value: number | undefined, digits = 3) {
  return value === undefined || value === null ? "—" : value.toFixed(digits);
}

function comparisonText(value: string) {
  return value.startsWith("No changed causal condition was declared")
    ? "没有声明新的关键条件；应先把它们当作可能相同的机制，而不是用新术语覆盖旧结论。"
    : value;
}

export function ReportView({
  report,
  isDemo,
  publicComputed,
  onEvidence,
  onDecision,
}: {
  report: Report;
  isDemo: boolean;
  publicComputed: boolean;
  onEvidence: () => void;
  onDecision: () => void;
}) {
  const [experimentOpen, setExperimentOpen] = useState(true);
  const failed = report.checks.filter((item) => item.status === "fail").length;
  const passed = report.checks.filter((item) => item.status === "pass").length;

  return (
    <div className="page report-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow-row">
            <span className="eyebrow">EVALUATION / {report.id.slice(0, 18)}</span>
            {isDemo && <span className="demo-chip">{publicComputed ? "浏览器内预检" : "样例报告"}</span>}
            {report.replay_of && <span className="demo-chip">历史回放</span>}
          </div>
          <h1>{report.attempt.title}</h1>
          <p>{report.attempt.idea}</p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" onClick={onEvidence}>
            查看证据链 <ArrowRight size={16} />
          </button>
          <button className="button button-dark" onClick={onDecision} disabled={isDemo} title={isDemo ? (publicComputed ? "公开版不写入终审；启动本地服务后可保存" : "样例报告不写入终审；请启动本地服务") : "保存人工终审"}>
            <UserCheck size={16} /> 人工终审
          </button>
        </div>
      </div>

      <section className={`decision-hero ${report.machine_decision.toLowerCase().replaceAll("_", "-")}`}>
        <div className="decision-main">
          <span className="section-kicker">基于证据的机器建议</span>
          <DecisionBadge decision={report.machine_decision} large />
          <h2>{reasonTitles[report.reason_code] ?? report.reason_code}</h2>
          <p>{reasonSummaries[report.reason_code] ?? report.summary}</p>
        </div>
        <div className="decision-stats">
          <div><strong>{passed}</strong><span>通过检查</span></div>
          <div><strong>{failed}</strong><span>失败门槛</span></div>
          <div><strong>{report.evidence_ids.length}</strong><span>引用证据</span></div>
          <div><strong>{report.comparisons.length}</strong><span>历史比较</span></div>
        </div>
      </section>

      <details className="audit-details">
        <summary>查看技术审计信息</summary>
        <div className="report-meta-strip">
          <span><Clock3 size={14} /> 证据截止 {new Date(report.cutoff).toLocaleString("zh-CN", { hour12: false })}</span>
          <span title="点击选中完整 run ID，用于历史回放">运行 ID <code>{report.id}</code></span>
          <span><Database size={14} /> {report.versions.retrieval}</span>
          <span><GitCompareArrows size={14} /> {report.versions.model}</span>
        </div>
        <div className="audit-footer">
          <span>SNAPSHOT {report.snapshot_hash?.slice(0, 20) ?? "not-recorded"}</span>
          <span>CONTEXT {report.context_refs.length ? `${report.context_refs.length} refs pinned` : "not available"}</span>
          <span>EMBEDDING {report.versions.embedding}</span>
        </div>
      </details>

      {report.regression && (
        <section className="panel regression-result-panel">
          <div className="panel-heading">
            <div><span className="section-kicker">REPLAY ASSERTIONS</span><h2>历史回归结果</h2></div>
            <span className={`regression-outcome ${report.regression.passed ? "passed" : "failed"}`}>{report.regression.passed ? "回归通过" : "回归失败"}</span>
          </div>
          <div className="regression-result-summary">
            <span>源运行 <code>{report.replay_of}</code></span>
            <span>预期建议 <DecisionBadge decision={report.regression.expected_decision} /></span>
            <span>实际建议 <DecisionBadge decision={report.regression.actual_decision} /></span>
          </div>
          <div className="check-list regression-assertions">
            {Object.entries(report.regression.assertions).map(([name, assertionPassed]) => {
              const Icon = assertionPassed ? Check : X;
              return <div className={`check-item ${assertionPassed ? "check-pass" : "check-fail"}`} key={name}><Icon size={17} /><div><strong>{regressionLabels[name] ?? name}</strong><span>{name}</span></div></div>;
            })}
          </div>
          <p className="regression-note">{report.regression.note}</p>
        </section>
      )}

      <div className="report-grid">
        <section className="panel comparisons-panel">
          <div className="panel-heading">
            <div><span className="section-kicker">01 / 历史证据</span><h2>过去最接近的尝试</h2></div>
            <span className="panel-count">{report.comparisons.length} 条</span>
          </div>
          {report.comparisons.length === 0 ? (
            <div className="empty-state">没有符合 cutoff 与结构化条件的历史机制。补一段更具体的机制描述，或把相关资料收进馆藏后再查。</div>
          ) : (
            <div className="comparison-list">
              {report.comparisons.map((comparison, index) => (
                <article className="comparison-card" key={comparison.attempt_id}>
                  <div className="comparison-index">{String(index + 1).padStart(2, "0")}</div>
                  <div className="comparison-body">
                    <div className="comparison-title-row">
                      <div><h3>{comparison.title}</h3><span>{comparison.task}</span></div>
                      {comparison.historical_decision && <DecisionBadge decision={comparison.historical_decision} />}
                    </div>
                    <p>{comparisonText(comparison.mechanism_difference)}</p>
                    <details className="retrieval-details"><summary>查看机制比较与检索分数</summary><div className="score-grid">
                      <div><span>机制相似度</span><strong>{number(comparison.mechanism_similarity, 2)}</strong></div>
                      <div><span>向量距离</span><strong>{number(comparison.vector_distance)}</strong></div>
                      <div><span>全文原分</span><strong>{number(comparison.fts_score, 2)}</strong></div>
                      <div><span>RRF 融合分</span><strong>{number(comparison.fused_score, 5)}</strong></div>
                    </div></details>
                    <button className="text-button" onClick={onEvidence}>
                      {comparison.evidence.length} 条可定位证据 <ArrowRight size={14} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel checks-panel">
          <div className="panel-heading">
            <div><span className="section-kicker">02 / 检查依据</span><h2>为什么这样建议</h2></div>
            <span className="version-chip">{report.versions.rules}</span>
          </div>
          <div className="check-list">
            {report.checks.map((item) => {
              const Icon = checkIcons[item.status];
              return (
                <div className={`check-item check-${item.status}`} key={item.name}>
                  <Icon size={17} aria-label={item.status} />
                  <div><strong>{checkLabels[item.name] ?? item.name}</strong><span>{item.reason_code}</span><p>{checkDetails[item.reason_code] ?? item.detail}</p></div>
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <section className="panel experiment-panel">
        <button className="experiment-heading" onClick={() => setExperimentOpen((value) => !value)} aria-expanded={experimentOpen}>
          <div className="experiment-title"><FlaskConical size={22} /><div><span className="section-kicker">03 / MINIMUM EXPERIMENT</span><h2>最小判别实验，而非追加工程投入</h2></div></div>
          <ChevronDown className={experimentOpen ? "rotate" : ""} size={20} />
        </button>
        {experimentOpen && (
          <div className="experiment-grid">
            {[
              ["判别假设", report.minimal_experiment.hypothesis],
              ["唯一干预", report.minimal_experiment.intervention],
              ["最强控制", report.minimal_experiment.control],
              ["预注册指标", report.minimal_experiment.metric],
              ["通过阈值", report.minimal_experiment.threshold],
              ["停止条件", report.minimal_experiment.stop_condition],
            ].map(([label, value]) => <div key={label}><span>{label}</span><p>{value}</p></div>) }
          </div>
        )}
      </section>

    </div>
  );
}
