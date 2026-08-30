import { Navigate, useNavigate, useParams } from "react-router";

import { CustomerDetailView } from "../components/customers/CustomerDetailView";
import { useHasPermission } from "../auth";
import { Alert } from "../ui";

export function CustomerDetailRoute() {
  const { customerId } = useParams();
  const navigate = useNavigate();
  const canRead = useHasPermission("COMPANY_CUSTOMER_READ");

  if (!customerId) {
    return <Navigate replace to="/customers" />;
  }
  if (!canRead) return <Alert variant="danger">You are not authorized to view this Customer.</Alert>;

  return (
    <CustomerDetailView
      customerId={customerId}
      onBack={() => navigate("/customers")}
    />
  );
}
