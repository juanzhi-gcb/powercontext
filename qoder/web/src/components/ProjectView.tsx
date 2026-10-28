import { ArrowUpRight, BookOpen, CheckCircle2, Code2, Database, GitBranch, PackageCheck, TerminalSquare } from "lucide-react";

const repository = "https://github.com/AtoFuture/NullPath-Research-CI";

export function ProjectView() {
  return (
    <div className="page project-page">
      <div className="project-intro">
        <span className="eyebrow">QODER × OCEANBASE / 2026</span>
        <h1>开始之前，<br />先看看过去踩过的坑。</h1>
        <p>先把自己的论文笔记、复现记录和技术报告导入本地证据库，再用一句话检索相关历史、失败原因和原始出处。需要正式投入建议时，再完成确定性预检、人工终审和最小判别实验。</p>
        <div className="project-links"><a className="button button-dark" href={repository} target="_blank" rel="noreferrer"><GitBranch size={17} />代码仓库<ArrowUpRight size={15} /></a><a className="button button-secondary" href="#run-guide"><BookOpen size={17} />运行说明</a></div>
      </div>
      <section className="problem-statement"><span>真实痛点</span><p>历史候选问题、机制查重、对抗复核、工程审查和 GO / NO-GO 裁决分散在文档里，外部论文与团队踩坑记录也没有进入同一证据源。下一次选题时，团队重复查重、重复争论，甚至用未来结论误写过去。</p><strong>NO-GO 不等于科研失败。及时止损本身就是研究结果。</strong></section>
      <section className="project-section">
        <div className="section-number">01</div><div><span className="section-kicker">SYSTEM</span><h2>一条可核对的研究决策链</h2></div>
        <div className="architecture-flow">
          {["导入自己的研究资料", "秘书提案，人工接受知识线", "seekdb 证据库 + PowerContext 记忆", "一句话检索历史与出处", "按需完成确定性预检", "人工终审、实验回流与历史回放"].map((item, index) => <div key={item}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item}</strong></div>)}
        </div>
      </section>
      <section className="project-section tech-section">
        <div className="section-number">02</div><div><span className="section-kicker">TECHNOLOGY</span><h2>指定技术各自承担真实职责</h2></div>
        <div className="tech-grid">
          <article><Database size={24} /><h3>seekdb / 研究事实源</h3><p>保存外部资料的原文、日期、稳定 locator 与研究尝试、证据、比较和运行；执行向量距离、全文相关性与任务、状态、时间过滤。</p></article>
          <article><PackageCheck size={24} /><h3>PowerContext / 连续工作台</h3><p>显式 Atomic Memory 保存研究约束、活跃指针和人工接受的知识线。运行只记录 Artifact ID、revision 与 hash，回放读取精确修订。</p></article>
          <article><Code2 size={24} /><h3>Qoder / 开发与交付</h3><p>需求拆解、FastAPI 与 React 实现、调试、回归验证和 Qoder Sites 发布均保留开发记录。</p></article>
        </div>
      </section>
      <section className="project-section run-section" id="run-guide">
        <div className="section-number">03</div><div><span className="section-kicker">REPRODUCE</span><h2>从安装到验证</h2></div>
        <div className="run-grid">
          <div className="run-steps">
            {[
              ["准备环境", "Docker Desktop、Python 3.12、Node 24+；无需模型 Key 即可运行固定响应模式。"],
              ["启动完整链路", "在 qoder/ 执行 docker compose -f deploy/compose.yaml up --build。"],
              ["打开工作台", "访问 http://127.0.0.1:5173；API 文档位于 http://127.0.0.1:8080/docs。"],
              ["导入自己的资料", "在「研究资料库」选择 Markdown/TXT，填写原文日期与出处；重复导入会自动跳过。"],
              ["让秘书梳理", "在「研究秘书」审阅知识线、疑似重复或孤立资料提案；只有接受的知识线写入 PowerContext。"],
              ["执行黄金验证", "启动独立 validation profile，再在 qoder/server 运行 uv run python ../evaluation/run_golden.py。"],
            ].map(([title, text], index) => <div className="run-step" key={title}><span>{index + 1}</span><div><h3>{title}</h3><p>{text}</p></div></div>)}
          </div>
          <div className="terminal-card"><div><TerminalSquare size={17} /><span>terminal</span></div><pre><code>cd qoder{`\n`}docker compose -f deploy/compose.yaml up --build{`\n\n`}# another terminal{`\n`}cd qoder{`\n`}docker compose -f deploy/compose.yaml --profile validation up -d --build validation-api{`\n`}cd server{`\n`}uv sync --extra dev{`\n`}uv run pytest{`\n`}uv run python ../evaluation/run_golden.py</code></pre></div>
        </div>
        <div className="verification-note"><CheckCircle2 size={18} /><p>初始数据、输入、操作步骤、预期结果和技术作用记录位于仓库 <code>qoder/examples/</code> 与 <code>qoder/evidence/</code>。资料库验收使用 arXiv 公开论文摘要验证导入与检索链路，不声称它是用户自己的实验结果；演示卡为依据框架重建的功能验证材料。研究秘书为确定性提案，不调用模型；接受的知识线只进入预检上下文，不修改证据与裁决。</p></div>
      </section>
      <footer className="project-footer"><div><strong>NullPath / Research CI</strong><span>Build with Qoder · seekdb · PowerContext</span></div><a href={repository} target="_blank" rel="noreferrer">查看源码与提交记录<ArrowUpRight size={15} /></a></footer>
    </div>
  );
}
