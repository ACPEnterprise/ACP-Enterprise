import { Navigate, useLocation } from "react-router";

export function ServiceBoardRedirect() {
  const location = useLocation();
  const target = new URLSearchParams(location.search);
  return <Navigate replace to={`/dispatch${target.toString() ? `?${target.toString()}` : ""}`} />;
}
