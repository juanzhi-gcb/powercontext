import { Brain, Database, FileClock, GitCommitHorizontal, ShieldCheck } from "lucide-react";
import type { Health } from "../types";

function pretty(text: string) {
  try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
}

export function ContextView({ health, isDemo }: { health: Health; isDemo: boolean }) {
  const entries = health.powercontext.entries ?? [];
  return (
    <div className="page context-page">
      <div className="page-heading"><div><span className="eyebrow">CONTEXT / CONTINUOUS WORKBENCH</span><h1>事实留在库里，工作状态跟着走</h1><p>PowerContext 保存约束、当前目标、活跃指针和交接，不复制 seekdb 的裁决正文。</p></div>{isDemo && <span className="demo-chip">静态修订示例</span>}</div>
      <section className="storage-split">
        <div><Database size={25} /><span className="section-kicker">SOURCE OF TRUTH</span><h2>seekdb</h2><p>尝试、机制、证据、比较、实验、机器建议和人工裁决。</p><span className={`service-status status-${health.seekdb.status}`}>{health.seekdb.status}</span></div>
        <div><Brain size={25} /><span className="section-kicker">REBUILDABLE WORKBENCH</span><h2>PowerContext</h2><p>研究宪法、活跃合同、可重建 ID 指针与 Handoff 修订。</p><span className={`service-status status-${health.powercontext.status}`}>{health.powercontext.status}</span></div>
      </section>
      <div className="context-scope"><ShieldCheck size={16} /><span>Scope</span><code>{health.powercontext.scope_id ?? "not configured"}</code></div>
      <section className="context-list">
        {entries.map((entry) => {
          const reference = health.powercontext.references?.find((item) => item.artifact_id === entry.artifact_id && item.revision === entry.revision && item.kind === entry.kind);
          const sha256 = entry.sha256 ?? reference?.sha256;
          return (
            <article className="context-card" key={`${entry.kind}-${entry.artifact_id}`}>
              <div className="context-card-heading"><div><FileClock size={19} /><h2>{entry.kind}</h2></div><span><GitCommitHorizontal size={15} />revision {entry.revision}</span></div>
              <pre>{pretty(entry.text)}</pre>
              <footer><span>{entry.artifact_id}</span><code>sha256 {sha256 ? sha256.slice(0, 16) : "not returned"}</code></footer>
            </article>
          );
        })}
        {!entries.length && <div className="empty-state">尚未读取到上下文条目。完成一次预检和人工终审后，这里会显示真实修订。</div>}
      </section>
      <div className="context-principle"><strong>写入顺序</strong><span>裁决先提交 seekdb</span><span>→</span><span>再更新 PowerContext 指针</span><span>→</span><span>指针失败可从事实库重建</span></div>
    </div>
  );
}
