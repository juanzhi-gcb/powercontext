import { useState, type FormEvent } from "react";
import { Check, FlaskConical, LoaderCircle, Play, ShieldAlert, TimerReset } from "lucide-react";
import { api } from "../api";
import { goldenCases } from "../sample";
import type { Decision, Report } from "../types";
import { DecisionBadge } from "./DecisionBadge";

export function RegressionView({ disabled, onComplete }: { disabled: boolean; onComplete: (report: Report) => void }) {
  const [runId, setRunId] = useState("");
  const [expected, setExpected] = useState<Decision>("CONDITIONAL_GO");
  const [required, setRequired] = useState("codealign-mechanism-2026-01-15");
  const [forbidden, setForbidden] = useState("codealign-engineering-2026-03-15");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const report = await api.replay(runId.trim(), expected, required.split(",").map((item) => item.trim()).filter(Boolean), forbidden.split(",").map((item) => item.trim()).filter(Boolean));
      onComplete(report);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "回放失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="page regression-page">
      <div className="page-heading"><div><span className="eyebrow">REGRESSION / GOLDEN CASES</span><h1>让旧裁决成为下一次的回归测试</h1><p>验证关键反例、原因和硬门槛，而不是比较一段看似合理的生成文案。</p></div></div>
      <section className="regression-summary">
        <div><TimerReset size={24} /><span>时间截断</span><strong>统一 cutoff</strong></div>
        <div><FlaskConical size={24} /><span>黄金案例</span><strong>5 条</strong></div>
        <div><ShieldAlert size={24} /><span>未来泄漏</span><strong>显式断言</strong></div>
      </section>
      <section className="panel golden-panel">
        <div className="panel-heading"><div><span className="section-kicker">FROZEN VALIDATION SET</span><h2>验证样例与预期</h2></div><span className="panel-count">evaluation/golden_cases.json</span></div>
        <div className="golden-table" role="table" aria-label="黄金回放样例">
          <div className="golden-row golden-header" role="row"><span>案例</span><span>预期建议</span><span>必须召回</span><span>回归边界</span></div>
          {goldenCases.map((item, index) => (
            <div className="golden-row" role="row" key={item.name}>
              <span><i>{String(index + 1).padStart(2, "0")}</i><strong>{item.name}</strong></span>
              <span><DecisionBadge decision={item.expected as Decision} /></span>
              <code>{item.evidence}</code>
              <span>{item.boundary}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="panel replay-panel">
        <div className="panel-heading"><div><span className="section-kicker">LIVE REPLAY</span><h2>回放一条真实运行</h2></div></div>
        <p className="panel-intro">读取原 run 固定的 cutoff 与 PowerContext 精确修订，不读取当前活跃指针。</p>
        {disabled ? <div className="notice notice-demo">静态网站不执行回放。请启动本地 Compose validation profile 后运行 <code>uv run python ../evaluation/run_golden.py</code>，或启动完整 Compose 后使用此表单。</div> : (
          <form onSubmit={submit} className="replay-form">
            <label className="full-width">源 evaluation_run ID<input required value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="从预检报告复制 run ID" /></label>
            <label>预期建议<select value={expected} onChange={(event) => setExpected(event.target.value as Decision)}><option value="NO_GO">NO_GO</option><option value="CONDITIONAL_GO">CONDITIONAL_GO</option><option value="INSUFFICIENT_EVIDENCE">INSUFFICIENT_EVIDENCE</option></select></label>
            <label>必须召回的证据 ID<input value={required} onChange={(event) => setRequired(event.target.value)} /></label>
            <label className="full-width">禁止出现的证据 ID<input value={forbidden} onChange={(event) => setForbidden(event.target.value)} /></label>
            {error && <div className="notice notice-error full-width">{error}</div>}
            <button className="button button-dark" disabled={pending}>{pending ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}运行历史回放</button>
          </form>
        )}
      </section>
      <div className="regression-rule"><Check size={17} /><p>仅声称“输入证据无未来泄漏”。当前 LLM 的训练知识可能包含未来信息，不作为时间隔离的保证。</p></div>
    </div>
  );
}
