interface AIWorkspaceProps {
  readonly open?: boolean;
}

export function AIWorkspace({ open = false }: AIWorkspaceProps) {
  if (!open) return null;
  return <aside aria-label="AI workspace" className="w-96 border-l border-stroke bg-surface" />;
}
