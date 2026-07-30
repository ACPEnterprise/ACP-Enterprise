import { Navigate, useNavigate, useParams } from "react-router";

import { CustomerDetailView } from "../components/customers/CustomerDetailView";

export function CustomerDetailRoute() {
  const { customerId } = useParams();
  const navigate = useNavigate();

  if (!customerId) {
    return <Navigate replace to="/customers" />;
  }

  return (
    <CustomerDetailView
      customerId={customerId}
      onBack={() => navigate("/customers")}
    />
  );
}
