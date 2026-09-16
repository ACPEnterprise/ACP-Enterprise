import type { LiaResponse } from "../../types/lia";

export const spokenAnswer = (result: LiaResponse) => {
  const fullAnswer = result.answer.trim();
  const sentences = fullAnswer.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [fullAnswer];
  const answer = sentences
    .slice(0, 2)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 480);
  const next = result.safe_next_action?.trim();
  if (!next || answer.includes(next)) return answer;
  return `${answer} Next: ${next}.`;
};
