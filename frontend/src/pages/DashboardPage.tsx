import { Dashboard } from "../components/dashboard/Dashboard";
import { useDashboard } from "../hooks/useDashboard";
import { getGatewayWsUrl } from "../lib/gatewayConfig";

export function DashboardPage() {
  const dashboard = useDashboard(getGatewayWsUrl());
  return <Dashboard {...dashboard} />;
}
