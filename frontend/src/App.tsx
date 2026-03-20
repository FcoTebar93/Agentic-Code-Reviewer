import { useDashboard } from "./hooks/useDashboard";
import { Dashboard } from "./components/dashboard/Dashboard";
import { getGatewayWsUrl } from "./lib/gatewayConfig";

export default function App() {
  const dashboard = useDashboard(getGatewayWsUrl());
  return <Dashboard {...dashboard} />;
}
