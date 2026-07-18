import { createContext, useContext } from "react";

export interface FieldContextValue {
  controlId: string;
  describedBy?: string;
  invalid: boolean;
  required: boolean;
  disabled: boolean;
}

export const FieldContext = createContext<FieldContextValue | null>(null);

export function useFieldContext(): FieldContextValue | null {
  return useContext(FieldContext);
}

export function combineIds(...ids: Array<string | undefined>): string | undefined {
  const combined = ids.filter(Boolean).join(" ");
  return combined || undefined;
}
