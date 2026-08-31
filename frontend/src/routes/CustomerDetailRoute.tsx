import { Navigate, useNavigate, useParams } from "react-router";

import { CustomerDetailView } from "../components/customers/CustomerDetailView";
import { useHasPermission } from "../auth";
import { Alert, Button } from "../ui";

export function CustomerDetailRoute() {
  const { customerId } = useParams();
  const navigate = useNavigate();
  const canRead = useHasPermission("COMPANY_CUSTOMER_READ");
  const canReadRelated = [
    useHasPermission("COMPANY_JOB_READ"),
    useHasPermission("COMPANY_ESTIMATE_READ"),
    useHasPermission("COMPANY_INVOICE_READ"),
    useHasPermission("COMPANY_SERVICE_AGREEMENT_READ"),
  ].some(Boolean);

  if (!customerId) {
    return <Navigate replace to="/customers" />;
  }
  if (!canRead) return <Alert variant="danger">You are not authorized to view this Customer.</Alert>;

  return (
    <div className="min-w-0 space-y-4">
      {canReadRelated ? (
        <div className="flex justify-end">
          <Button
            variant="secondary"
            onClick={() =>
              navigate(
                `/lia?contextDomain=customers&contextId=${encodeURIComponent(customerId)}`,
              )
            }
          >
            Ask LIA about this Customer
          </Button>
        </div>
      ) : null}
      <CustomerDetailView
        customerId={customerId}
        onBack={() => navigate("/customers")}
      />
    </div>
  );
}
