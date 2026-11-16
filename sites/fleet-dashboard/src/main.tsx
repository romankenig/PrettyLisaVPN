import { createRoot } from "react-dom/client";
import Dashboard from "./Dashboard";
import ProductAnalytics from "./ProductAnalytics";
import AvailabilityPage from "./AvailabilityPage";
import AppVersions from "./AppVersions";
import { reportPage } from "./reportRoutes";
import "./style.css";
const page = reportPage(window.location.pathname);
createRoot(document.getElementById("root")!).render(page === "versions" ? <AppVersions /> : page === "product" ? <ProductAnalytics /> : page === "methods" || page === "services" ? <AvailabilityPage kind={page} /> : <Dashboard />);
