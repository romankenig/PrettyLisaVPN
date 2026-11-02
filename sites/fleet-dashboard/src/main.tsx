import { createRoot } from "react-dom/client";
import Dashboard from "./Dashboard";
import ProductAnalytics from "./ProductAnalytics";
import "./style.css";
createRoot(document.getElementById("root")!).render(window.location.pathname.replace(/\/$/, "") === "/dashboard/product-analytics" ? <ProductAnalytics /> : <Dashboard />);
