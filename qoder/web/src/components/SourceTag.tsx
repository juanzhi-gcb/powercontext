const sourceLabels: Record<string, string> = {
  "rescience-c": "ReScience 复现",
  fred: "FReD 复现",
  "retraction-watch": "撤稿记录",
};

const typeLabels: Record<string, string> = {
  replication: "外部复现",
  retraction: "撤稿记录",
};

const outcomeLabels: Record<string, string> = {
  failed: "未能重现",
  mixed: "结果混合",
  successful: "重现成功",
  retracted: "已撤稿",
};

export function sourceMetaLead(source: string | undefined, recordType: string | undefined, outcome: string | undefined, fallback: string) {
  if (!source) return fallback;
  const outcomeLabel = outcome ? outcomeLabels[outcome] : "";
  return outcomeLabel || (recordType === "retraction" ? "撤稿记录" : "外部复现");
}

export function SourceTag({ source, recordType, url }: { source?: string; recordType?: string; url?: string }) {
  const label = source ? sourceLabels[source] : recordType ? typeLabels[recordType] : "";
  if (!label) return null;
  const className = `hall-source-tag is-${recordType ?? "external"}`;
  if (!url) return <span className={className}>{label}</span>;
  return <a className={className} href={url} target="_blank" rel="noreferrer" title="打开外部数据来源">{label}</a>;
}
