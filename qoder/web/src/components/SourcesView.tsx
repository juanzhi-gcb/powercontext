import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Database, FileText, GitBranch, Library, LoaderCircle, LockKeyhole, Search, Upload } from "lucide-react";
import { api, staticDemo } from "../api";
import type { ResearchSourceInput, SourceRecord } from "../types";

const demoSources: SourceRecord[] = [
  {
    attempt_id: "source-demo-attention",
    title: "Attention Is All You Need",
    task: "sequence-transduction",
    domain: "research",
    available_at: "2017-06-12T00:00:00+00:00",
    evidence_count: 1,
    source_type: "paper",
    locator: "https://arxiv.org/abs/1706.03762",
    published_at: "2017-06-12T00:00:00+00:00",
    imported_at: "2026-10-27T00:00:00+00:00",
  },
];

function sourceTitle(file: File, content: string) {
  const heading = content.match(/^#\s+(.+)$/m)?.[1]?.trim();
  return (heading || file.name.replace(/\.(md|markdown|txt)$/i, "")).slice(0, 300);
}

export function SourcesView({ live, onSearch, onSecretary }: { live: boolean; onSearch: () => void; onSecretary: () => void }) {
  const [sources, setSources] = useState<SourceRecord[]>(staticDemo ? demoSources : []);
  const [files, setFiles] = useState<File[]>([]);
  const [publishedDate, setPublishedDate] = useState(new Date().toISOString().slice(0, 10));
  const [sourceUrl, setSourceUrl] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!live) return;
    let active = true;
    api.listSources().then((items) => {
      if (active) setSources(items);
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "资料库读取失败");
    });
    return () => { active = false; };
  }, [live]);

  async function importFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setPending(true);
    setError("");
    setMessage("");
    try {
      if (!files.length) throw new Error("请先选择至少一份 Markdown 或 TXT 资料");
      if (files.length > 10) throw new Error("每次最多导入 10 份资料");
      const inputs: ResearchSourceInput[] = await Promise.all(files.map(async (file) => {
        const content = (await file.text()).trim();
        if (content.length < 10) throw new Error(`${file.name} 内容不足 10 个字符`);
        if (content.length > 50000) throw new Error(`${file.name} 超过 50,000 字符，请先拆分文件`);
        const path = file.webkitRelativePath || file.name;
        return {
          title: sourceTitle(file, content),
          content,
          locator: files.length === 1 && sourceUrl.trim() ? sourceUrl.trim() : `local-library/${path}`,
          published_at: new Date(`${publishedDate}T00:00:00Z`).toISOString(),
          source_type: "paper",
          task: "research",
          domain: "research",
        };
      }));
      const result = await api.importSources(inputs);
      setMessage(`已导入 ${result.imported} 个资料分段，跳过 ${result.skipped} 个重复分段。`);
      setFiles([]);
      setSourceUrl("");
      form.reset();
      setSources(await api.listSources());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "资料导入失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="page sources-page">
      <div className="page-heading">
        <div><span className="eyebrow">YOUR LIBRARY / TRACEABLE EVIDENCE</span><h1>把你的研究资料，变成可检索的证据。</h1><p>导入自己的论文笔记、复现记录和技术报告。系统保留原文、资料日期与出处，用于真实历史检索，不依赖内置的个人经验。</p></div>
        <div className="heading-actions"><button className="button button-secondary" onClick={onSecretary}><GitBranch size={16} />让秘书梳理</button><button className="button button-dark" onClick={onSearch}><Search size={16} />去检索想法<ArrowRight size={15} /></button></div>
      </div>

      {!live && <div className="notice notice-demo"><LockKeyhole size={18} /><div><strong>{staticDemo ? "公开网站仅展示样例资料" : "本地研究服务尚未连接"}</strong><p>真实导入只写入你自己的本地 seekdb，不会上传到 Qoder Sites。请按「项目与复现」启动本地服务。</p></div></div>}

      <section className="source-import-layout">
        <form className="source-import-panel" onSubmit={importFiles}>
          <div className="source-import-title"><Upload size={20} /><div><h2>连接本地研究资料</h2><p>第一版支持 Markdown 和 TXT；长文自动分段，重复内容不会重复写入。</p></div></div>
          <label className="source-file-picker">选择资料文件
            <input type="file" accept=".md,.markdown,.txt" multiple disabled={!live || pending} onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
            <small>最多 10 份，每份不超过 50,000 字符。文件内容会发送到当前本地 API。</small>
          </label>
          {files.length > 0 && <div className="source-file-list">{files.map((file) => <span key={`${file.name}-${file.lastModified}`}><FileText size={14} />{file.name}</span>)}</div>}
          <label>资料日期<input type="date" required value={publishedDate} disabled={!live || pending} onChange={(event) => setPublishedDate(event.target.value)} /><small>用于历史时间边界；请填写原文发表或记录形成日期，而不是默认导入日。</small></label>
          <label>原始出处链接（单文件可选）<input type="url" value={sourceUrl} disabled={!live || pending} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://arxiv.org/abs/…" /><small>填写论文或报告的原始链接；留空则使用本地文件名。批量导入时分别使用各文件名。</small></label>
          <button className="button button-accent" disabled={!live || pending}>
            {pending ? <LoaderCircle className="spin" size={17} /> : <Database size={17} />}
            {pending ? "正在写入证据库" : "导入到本地证据库"}
          </button>
        </form>
        <aside className="source-principles">
          <Library size={23} />
          <h2>资料不是一句向量</h2>
          <ul><li>原文进入 seekdb 混合检索</li><li>每个分段保留稳定 ID 与 locator</li><li>资料日期参与 cutoff 时间隔离</li><li>检索结果始终展示原文出处</li></ul>
        </aside>
      </section>

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {message && <div className="notice source-success" role="status">{message}<button className="text-button" onClick={onSearch}>现在检索<ArrowRight size={14} /></button></div>}

      <section className="panel source-library">
        <div className="panel-heading"><div><span className="section-kicker">PERSISTENT LIBRARY</span><h2>已连接的研究资料</h2></div><span className="panel-count">{sources.length} 个可追溯资料分段</span></div>
        {!sources.length && <div className="empty-state">还没有外部资料。导入第一份研究笔记后，就可以从「档案馆大厅」真实检索它。</div>}
        <div className="source-record-list">{sources.map((source) => <article className="source-record" key={source.attempt_id}>
          <FileText size={18} />
          <div><h3>{source.title}</h3>{/^https?:\/\//.test(source.locator) ? <a href={source.locator} target="_blank" rel="noreferrer">{source.locator}</a> : <code>{source.locator}</code>}</div>
          <div className="source-record-meta"><span>{source.source_type} · {source.evidence_count} 条证据</span><time>{source.published_at.slice(0, 10)}</time></div>
        </article>)}</div>
      </section>
    </div>
  );
}
