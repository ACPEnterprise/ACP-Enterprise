import { ChevronLeft, ChevronRight } from "lucide-react";
import { Link } from "react-router";

import type { EngineeringCommandPage } from "../../types/engineeringControl";
import { Badge, Button } from "../../ui";
import { engineeringLabel, shortHead, timestamp } from "./presentation";

interface Props {
  data: EngineeringCommandPage;
  onPage: (page: number) => void;
}

export function EngineeringCommandList({ data, onPage }: Props) {
  return (
    <>
      <div className="grid gap-3 p-ui-4">
        {data.items.map((command) => (
          <article
            key={command.id}
            className="grid min-w-0 gap-3 rounded-lg border border-stroke p-ui-4 md:grid-cols-[1.1fr_1fr_auto]"
          >
            <div className="min-w-0">
              <Link
                className="text-lg font-bold text-blue-400 hover:underline"
                to={`/engineering/${command.id}`}
              >
                {command.ecid}
              </Link>
              <p className="mt-1 text-sm text-content-muted">
                {engineeringLabel(command.command_type)}
              </p>
            </div>
            <dl className="grid min-w-0 gap-2 text-sm sm:grid-cols-2">
              <div><dt className="text-content-muted">Repository</dt><dd>{command.repository_key}</dd></div>
              <div><dt className="text-content-muted">Branch</dt><dd className="break-all">{command.expected_branch}</dd></div>
              <div><dt className="text-content-muted">Expected HEAD</dt><dd><code>{shortHead(command.expected_head)}</code></dd></div>
              <div><dt className="text-content-muted">Created</dt><dd>{timestamp(command.created_at)}</dd></div>
              <div><dt className="text-content-muted">Expires</dt><dd>{timestamp(command.expires_at)}</dd></div>
              <div><dt className="text-content-muted">Change level</dt><dd>{command.requested_code_changes ? "Uncommitted code changes" : "Inspection only"}</dd></div>
            </dl>
            <div className="flex flex-wrap items-start gap-2 md:max-w-48 md:flex-col">
              <Badge>{engineeringLabel(command.approval_state)}</Badge>
              <Badge>{engineeringLabel(command.execution_state)}</Badge>
            </div>
          </article>
        ))}
      </div>
      {data.total_pages > 0 && (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-stroke p-ui-4 text-sm text-content-muted">
          <span>Page {data.page} of {data.total_pages} · {data.total_count} commands</span>
          <div className="flex gap-2">
            <Button variant="outline" aria-label="Previous page" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}><ChevronLeft size={18} /></Button>
            <Button variant="outline" aria-label="Next page" disabled={data.page >= data.total_pages} onClick={() => onPage(data.page + 1)}><ChevronRight size={18} /></Button>
          </div>
        </footer>
      )}
    </>
  );
}
