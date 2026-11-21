import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { acceptAccessAgreement } from "../api/accessAgreements";
import { useAuth } from "../auth";
import { useCurrentAccessAgreement } from "../hooks/useAccessAgreement";
import { Alert, Button, Card, Spinner } from "../ui";

export function AccessAgreementRoute() {
  const navigate = useNavigate();
  const { activeCompany, signOut } = useAuth();
  const agreement = useCurrentAccessAgreement(activeCompany?.id);
  const [reviewed, setReviewed] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const accepting = agreement.isFetching;

  const downloadAgreement = () => {
    if (!agreement.data?.content || !agreement.data.title) return;
    const blob = new Blob([agreement.data.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${agreement.data.title.replaceAll(/[^a-z0-9]+/gi, "-").toLowerCase()}-v${agreement.data.version}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (agreement.isLoading) return <div className="flex min-h-screen items-center justify-center"><Spinner label="Loading required agreement" size="large" /></div>;
  if (agreement.isError) return <Alert variant="danger" title="Agreement unavailable">The required access agreement could not be loaded. Sign out and contact the administrator.</Alert>;
  if (!agreement.data?.required) return <Alert variant="danger" title="Agreement not required">No agreement is required for this account.</Alert>;
  if (!agreement.data.configured) return <Alert variant="danger" title="Agreement not configured">The required Demo access agreement has not been published. Contact the administrator.</Alert>;
  if (agreement.data.accepted) {
    return <AgreementAcceptedRedirect navigate={navigate} />;
  }
  const accept = async () => {
    if (!agreement.data?.agreement_id || !agreement.data.version || !reviewed || !consent) return;
    setError(null);
    try {
      await acceptAccessAgreement({ agreement_id: agreement.data.agreement_id, version: agreement.data.version, acknowledge_reviewed: reviewed, electronic_signature_consent: consent });
      navigate("/sales-demo", { replace: true });
    } catch {
      setError("The agreement could not be recorded. No protected Demo access was granted.");
    }
  };
  return <main className="mx-auto w-full max-w-4xl space-y-5 p-6" aria-labelledby="agreement-title">
    <Card className="primary-work-panel p-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-action-primary">Required before Demo access</p>
      <h1 id="agreement-title" className="mt-2 text-2xl font-bold">{agreement.data.title}</h1>
      <p className="mt-2 text-sm text-content-muted">Version {agreement.data.version} · Effective {agreement.data.effective_at ? new Date(agreement.data.effective_at).toLocaleDateString() : "current"}</p>
      <div className="mt-5 flex justify-end"><Button variant="secondary" onClick={downloadAgreement}>Download a copy</Button></div>
      <div className="mt-3 max-h-[55vh] overflow-y-auto rounded-lg border border-stroke bg-surface-subtle p-5 whitespace-pre-wrap text-sm leading-6">{agreement.data.content}</div>
      <div className="mt-5 space-y-3">
        <label className="flex gap-3 text-sm"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /> <span>I acknowledge that I have received and reviewed the complete TwelveHats Confidentiality, Non-Disclosure, Intellectual Property Protection &amp; Restricted System Access Agreement.</span></label>
        <label className="flex gap-3 text-sm"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> <span>I agree to be legally bound by the Agreement, consent to electronic execution, and intend my electronic acceptance to constitute my electronic signature.</span></label>
      </div>
      {error && <Alert className="mt-4" variant="danger">{error}</Alert>}
      <div className="mt-6 flex flex-wrap gap-3"><Button disabled={!reviewed || !consent || accepting} loading={accepting} onClick={() => void accept()}>I Agree, Electronically Sign &amp; Continue</Button><Button variant="secondary" onClick={() => void signOut()}>Decline &amp; Sign Out</Button></div>
    </Card>
  </main>;
}

function AgreementAcceptedRedirect({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  useEffect(() => { navigate("/sales-demo", { replace: true }); }, [navigate]);
  return null;
}
