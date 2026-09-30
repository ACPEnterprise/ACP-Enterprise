import {
  createDeliveryPlan,
  deliveryPlanPreservesSemantics,
  liaDeliveryStyle,
  type DeliveryCategory,
  type LiaDeliveryIntent,
} from "./voiceDelivery";
import type { SpokenResponseMode } from "./voiceSpeech";

export interface DeliveryAcceptanceCase {
  readonly id: string;
  readonly family: string;
  readonly text: string;
  readonly mode: SpokenResponseMode;
  readonly category: DeliveryCategory;
  readonly expectedIntent: LiaDeliveryIntent;
  readonly materialValues: readonly string[];
}

export const DELIVERY_NATURALNESS_CORPUS: readonly DeliveryAcceptanceCase[] = [
  { id: "FACT-01", family: "factual_answer", text: "The Smith customer is active, with seven Jobs on record.", mode: "NORMAL", category: "KNOWN", expectedIntent: "NEUTRAL_EXPLANATION", materialValues: ["Smith", "seven Jobs"] },
  { id: "BRIEF-01", family: "owner_brief", text: "Today, six appointments are scheduled; two still need your attention.", mode: "BRIEF", category: "KNOWN", expectedIntent: "OWNER_BRIEF", materialValues: ["six", "two"] },
  { id: "CLARIFY-01", family: "clarification", text: "Which Smith customer do you mean?", mode: "BRIEF", category: "UNCERTAIN", expectedIntent: "CLARIFICATION", materialValues: ["Smith"] },
  { id: "MISSING-01", family: "missing_evidence", text: "I found the Invoice, but settlement evidence is unavailable.", mode: "NORMAL", category: "LIMITED", expectedIntent: "NEUTRAL_EXPLANATION", materialValues: ["Invoice", "unavailable"] },
  { id: "PAYROLL-01", family: "payroll_blocker", text: "Lianne isn't payroll-ready yet. Compensation setup and accepted time are still missing.", mode: "NORMAL", category: "BLOCKER", expectedIntent: "WARNING", materialValues: ["Lianne", "Compensation", "accepted time"] },
  { id: "DISPATCH-01", family: "dispatch_warning", text: "Warning: this assignment conflicts with Jason's existing appointment at 2:00 PM.", mode: "NORMAL", category: "BLOCKER", expectedIntent: "WARNING", materialValues: ["Jason", "2:00 PM"] },
  { id: "POSITIVE-01", family: "positive_result", text: "The Appointment is confirmed and ready for Dispatch.", mode: "BRIEF", category: "KNOWN", expectedIntent: "REASSURANCE", materialValues: ["Appointment", "Dispatch"] },
  { id: "STEPS-01", family: "step_by_step", text: "First, complete compensation setup. Then approve the accepted time. Next, rerun readiness.", mode: "DETAILED", category: "BLOCKER", expectedIntent: "STEP_BY_STEP", materialValues: ["compensation", "accepted time", "readiness"] },
  { id: "ECON-01", family: "economic_answer", text: "Revenue is $12,450.00, but contribution remains unavailable because material cost is missing.", mode: "NORMAL", category: "LIMITED", expectedIntent: "NEUTRAL_EXPLANATION", materialValues: ["$12,450.00", "unavailable", "material cost"] },
  { id: "EMPLOYEE-01", family: "employee_context", text: "Lianne Hernandez is active in the MAIN Branch, and her Mobile readiness is complete.", mode: "NORMAL", category: "KNOWN", expectedIntent: "REASSURANCE", materialValues: ["Lianne Hernandez", "MAIN", "Mobile"] },
];

export function evaluateDeliveryCase(item: DeliveryAcceptanceCase) {
  const style = liaDeliveryStyle(item.mode, item.category);
  const baseline = { text: item.text, rate: style.platformMapping.relativeRate };
  const successor = createDeliveryPlan(item.text, style);
  return {
    baseline,
    successor,
    semanticEquivalent: deliveryPlanPreservesSemantics(successor),
    materialValuesPreserved: item.materialValues.every((value) =>
      successor.semanticText.includes(value),
    ),
  };
}
