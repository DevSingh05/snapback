import { useState } from "react";

import { BudgetFields, EMPTY_BUDGET, budgetToBrief, type BudgetForm } from "../search/BudgetFields";
import { PlacesStrip } from "../search/PlacesStrip";
import "./shell.css";

// The researched places as a list, filtered by the renter's own budget and must-haves. The
// same record-backed search the result page uses; nothing here says a place can be rented now.
export function ListingsPage() {
  const [form, setForm] = useState<BudgetForm>(EMPTY_BUDGET);
  return (
    <div className="view" data-testid="listings-page">
      <header className="view-head">
        <p className="view-eyebrow mono">Listings</p>
        <h1 className="view-title">Researched places</h1>
        <p className="view-lead">
          Places on CoStar&apos;s record, with what it showed at its last research. Set your budget
          and must-haves to narrow the list.
        </p>
      </header>
      <div className="view-body view-split">
        <div className="view-side">
          <BudgetFields value={form} onChange={setForm} />
        </div>
        <div className="view-main">
          <PlacesStrip caseId={null} brief={budgetToBrief(form)} heading="Places that fit" />
        </div>
      </div>
    </div>
  );
}
