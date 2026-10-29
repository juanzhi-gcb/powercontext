import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, Info, LoaderCircle, LockKeyhole, Play } from "lucide-react";
import type { AttemptInput, Report } from "../types";
import { api, staticDemo } from "../api";
import { domainForTask } from "../domains";
import { evaluatePublicAttempt } from "../publicEngine";

const example: AttemptInput = {
  title: "IBML identifiability narrow",
  idea: "Test when observable control statistics cannot identify reliability and complementarity separately.",
  mechanism: "Reliability and complementarity jointly determine collaboration performance, but observable control statistics may make the two factors unidentifiable.",
  task: "collaboration-analysis",
  domain: "multi-agent-systems",
  failure_condition: "A simple estimator identifies both factors or the observation restriction does not change the old conclusion.",
  assumptions: ["The observation map can be explicitly restricted"],
  competing_explanations: ["Simple weighted baseline", "Existing threshold estimator"],
  differentiator: "Restrict the observation map so control statistics are unidentifiable; test the boundary instead of redrawing the broad phase diagram.",
  available_at: "2026-02-02T00:00:00Z",
  gpu_count: 2,
  data_ready: true,
  checkpoint_ready: true,
  pilot_hours: 24,
  storage_gb: 100,
  baseline_first: false,
};

const blank: AttemptInput = {
  title: "",
  idea: "",
  mechanism: "",
  task: "general",
  domain: "",
  failure_condition: "如果核心机制在最小实验中不成立，或相对最强竞争解释没有可重复差异，则停止投入。",
  assumptions: [],
  competing_explanations: [],
  differentiator: "",
  available_at: new Date().toISOString(),
  gpu_count: 0,
  data_ready: false,
  checkpoint_ready: false,
  pilot_hours: 24,
  storage_gb: 100,
  baseline_first: false,
};

export function NewPrecheck({ disabled, draft, onComplete }: { disabled: boolean; draft: string; onComplete: (report: Report) => void }) {
  const [form, setForm] = useState(blank);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const set = <K extends keyof AttemptInput>(key: K, value: AttemptInput[K]) => setForm((current) => ({ ...current, [key]: value }));

  useEffect(() => {
    if (!draft) return;
    setForm((current) => ({
      ...current,
      title: current.title || draft.trim().split(/\s+/).slice(0, 6).join(" ").slice(0, 48),
      idea: draft,
      available_at: new Date().toISOString(),
    }));
  }, [draft]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const input = { ...form, domain: domainForTask(form.task) };
      if (staticDemo) {
        onComplete(await evaluatePublicAttempt(input));
        return;
      }
      const attempt = await api.createAttempt(input);
      const report = await api.evaluate(attempt.id, new Date().toISOString());
      onComplete(report);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "预检失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="page precheck-page">
      <div className="page-heading">
        <div><span className="eyebrow">完整预检 / 按需使用</span><h1>确认这个想法是否值得投入</h1><p>只需先写研究想法、可能成立的机制和与历史的差异。其余判断依据与工程条件可以按需补充。</p></div>
        <button type="button" className="button button-secondary" onClick={() => setForm(example)}><BookOpen size={16} />填入完整示例</button>
      </div>
      {disabled && (
        <div className="notice notice-demo"><LockKeyhole size={19} /><div><strong>{staticDemo ? "公开版在浏览器内实时计算预检" : "本地研究服务尚未连接"}</strong><p>{staticDemo ? "报告会根据你的输入，对公开馆藏执行真实的混合检索、机制比较与确定性检查；结果不写入 seekdb，也不读取 PowerContext。需要持久化与人工终审时，请在「项目与复现」启动本地服务。" : "当前仅展示已标注的演示报告，不会提交到伪后端。请在「项目与复现」中按步骤启动本地 seekdb + PowerContext，再提交真实预检。"}</p></div></div>
      )}
      <form className="precheck-form" onSubmit={submit}>
        <fieldset disabled={(!staticDemo && disabled) || pending}>
          <section className="form-section">
            <div className="form-section-title"><span>01</span><div><h2>说清研究想法</h2><p>先回答“为什么可能有效”，再谈模型和实验规模。</p></div></div>
            <div className="form-grid two-columns">
              <label className="full-width">给它一个名字<input required minLength={2} value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="例如：限制观察统计量的可识别性实验" /></label>
              <label className="full-width">你想研究什么？<textarea required minLength={10} rows={3} value={form.idea} onChange={(e) => set("idea", e.target.value)} placeholder="用自然语言描述问题和准备尝试的路线" /></label>
              <label className="full-width">你认为它为什么可能有效？<textarea required minLength={10} rows={3} value={form.mechanism} onChange={(e) => set("mechanism", e.target.value)} placeholder="写下起作用的机制，而不只是准备使用的方法名称" /><small>这段话会用于 seekdb 向量与全文混合检索。</small></label>
              <label className="full-width">和过去尝试相比，你改变了什么？（可留空）<textarea rows={3} value={form.differentiator} onChange={(e) => set("differentiator", e.target.value)} placeholder="例如：更换了关键因果条件，而不只是换数据集或换术语" /></label>
            </div>
          </section>

          <details className="form-details">
            <summary><span>02</span><div><strong>补充判断依据</strong><small>失败条件、隐含假设、竞争解释与时间设置</small></div></summary>
            <div className="form-grid two-columns">
              <label className="full-width">出现什么结果就应该停止？<textarea required rows={2} value={form.failure_condition} onChange={(e) => set("failure_condition", e.target.value)} /></label>
              <label>隐含假设（用分号分隔）<input value={form.assumptions.join("；")} onChange={(e) => set("assumptions", e.target.value.split(/[；;]/).filter(Boolean))} placeholder="例如：观察映射可以被显式限制" /></label>
              <label>最强竞争解释<input value={form.competing_explanations.join("；")} onChange={(e) => set("competing_explanations", e.target.value.split(/[；;]/).filter(Boolean))} placeholder="例如：简单加权基线也能解释结果" /></label>
              <label>任务标识<input required value={form.task} onChange={(e) => set("task", e.target.value)} /><small>用于按研究方向缩小检索范围；保留 general 表示检索全部馆藏。</small></label>
              <label>资料可用时间<input type="datetime-local" value={form.available_at.slice(0, 16)} onChange={(e) => set("available_at", new Date(e.target.value).toISOString())} /><small>历史回放时，不能早于这个时间评估该提案。</small></label>
            </div>
          </details>

          <section className="form-section">
            <div className="form-section-title"><span>03</span><div><h2>确认最小实验能开始</h2><p>这些条件由固定规则检查，不由模型主观猜测。</p></div></div>
            <div className="resource-grid">
              <label>可用 GPU 数量<input type="number" min={0} value={form.gpu_count} onChange={(e) => set("gpu_count", Number(e.target.value))} /></label>
              <label>首轮验证需要几小时？<input type="number" min={1} value={form.pilot_hours} onChange={(e) => set("pilot_hours", Number(e.target.value))} /></label>
              <label>可用存储（GB）<input type="number" min={0} value={form.storage_gb} onChange={(e) => set("storage_gb", Number(e.target.value))} /></label>
              <label className="toggle-field"><input type="checkbox" checked={form.data_ready} onChange={(e) => set("data_ready", e.target.checked)} /><span>最小数据已经就绪</span></label>
              <label className="toggle-field"><input type="checkbox" checked={form.checkpoint_ready} onChange={(e) => set("checkpoint_ready", e.target.checked)} /><span>模型版本已经固定</span></label>
              <label className="toggle-field"><input type="checkbox" checked={form.baseline_first} onChange={(e) => set("baseline_first", e.target.checked)} /><span>我是先选基线，再反推问题</span></label>
            </div>
          </section>
        </fieldset>
        {error && <div className="notice notice-error" role="alert">{error}</div>}
        <div className="form-submit-bar">
          <div><Info size={16} /><span>报告会给出建议、历史证据和最小判别实验；技术审计信息默认收起。</span></div>
          <button className="button button-accent" type="submit" disabled={(!staticDemo && disabled) || pending}>
            {pending ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />}
            {pending ? "正在生成避坑报告" : "生成避坑报告"}<ArrowRight size={16} />
          </button>
        </div>
      </form>
    </div>
  );
}
