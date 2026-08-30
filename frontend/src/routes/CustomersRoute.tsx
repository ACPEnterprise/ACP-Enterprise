import { CustomerManagement } from "../components/customers/CustomerManagement";
import { useHasPermission } from "../auth";
import { Alert } from "../ui";

export function CustomersRoute() {
  const canRead = useHasPermission("COMPANY_CUSTOMER_READ");
  if (!canRead) return <Alert variant="danger">You are not authorized to view Customers.</Alert>;
  return <CustomerManagement />;
}
