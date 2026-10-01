import { Navigate, useLocation } from "react-router";

export function ServiceBoardRedirect() {
  const location = useLocation();
  const target = new URLSearchParams(location.search);
  if (!target.has("view")) target.set("view", "day");
  target.set("perspective", "dispatch");
  return <Navigate replace to={`/scheduling?${target.toString()}`} />;
}
