import { CircleAlert, CircleCheck, CircleX, ShieldQuestion } from "lucide-react";
import type { Decision } from "../types";

const meta = {
  NO_GO: { label: "暂缓投入", className: "decision-no-go", Icon: CircleX },
  CONDITIONAL_GO: { label: "满足条件再做", className: "decision-conditional", Icon: CircleAlert },
  INSUFFICIENT_EVIDENCE: { label: "证据不足", className: "decision-insufficient", Icon: ShieldQuestion },
  GO: { label: "可以继续", className: "decision-go", Icon: CircleCheck },
};

export function DecisionBadge({ decision, large = false }: { decision: Decision; large?: boolean }) {
  const { label, className, Icon } = meta[decision];
  return (
    <span className={`decision-badge ${className} ${large ? "decision-badge-large" : ""}`}>
      <Icon aria-hidden="true" size={large ? 22 : 15} strokeWidth={1.8} />
      {label}
    </span>
  );
}
