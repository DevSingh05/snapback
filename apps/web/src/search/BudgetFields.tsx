import type { RenterBrief } from "../contracts";

// The optional "Your budget and must-haves" row on the first screen. Everything is a string or a
// flag here; budgetToBrief turns it into the API's RenterBrief and drops what is blank.
export interface BudgetForm {
  maxRent: string;
  beds: string; // "" any, "0" studio, "1".."4"
  noWalkup: boolean;
  parking: boolean;
  pets: boolean;
  moveInBy: string; // ISO date or ""
}

export const EMPTY_BUDGET: BudgetForm = {
  maxRent: "",
  beds: "",
  noWalkup: false,
  parking: false,
  pets: false,
  moveInBy: "",
};

export function budgetToBrief(b: BudgetForm): RenterBrief {
  const brief: RenterBrief = {};
  const rent = Number.parseInt(b.maxRent.split(".")[0]!.replace(/[^0-9]/g, ""), 10);
  if (Number.isFinite(rent) && rent > 0 && rent <= 1_000_000) brief.max_rent_month = rent;
  if (b.beds !== "") brief.beds_min = Number(b.beds);
  if (b.noWalkup) brief.needs_no_walkup = true;
  if (b.parking) brief.needs_parking = true;
  if (b.pets) brief.pets = true;
  if (b.moveInBy) brief.move_in_by = b.moveInBy;
  return brief;
}

export function BudgetFields({
  value,
  onChange,
}: {
  value: BudgetForm;
  onChange: (next: BudgetForm) => void;
}) {
  const set = <K extends keyof BudgetForm>(key: K, v: BudgetForm[K]) =>
    onChange({ ...value, [key]: v });
  return (
    <fieldset className="pf-budget" data-testid="budget-row">
      <legend>Your budget and must-haves (optional)</legend>
      <div className="pf-budget-grid">
        <label className="pf-field">
          Max rent a month
          <input
            type="text"
            inputMode="numeric"
            placeholder="1,800"
            autoComplete="off"
            value={value.maxRent}
            onChange={(e) => set("maxRent", e.target.value)}
          />
        </label>
        <label className="pf-field">
          Beds
          <select value={value.beds} onChange={(e) => set("beds", e.target.value)}>
            <option value="">Any</option>
            <option value="0">Studio or more</option>
            <option value="1">1 or more</option>
            <option value="2">2 or more</option>
            <option value="3">3 or more</option>
            <option value="4">4 or more</option>
          </select>
        </label>
        <label className="pf-field">
          Move in by
          <input
            type="date"
            value={value.moveInBy}
            onChange={(e) => set("moveInBy", e.target.value)}
          />
        </label>
      </div>
      <div className="pf-checks">
        <label className="pf-check">
          <input
            type="checkbox"
            checked={value.noWalkup}
            onChange={(e) => set("noWalkup", e.target.checked)}
          />
          No walk-up
        </label>
        <label className="pf-check">
          <input
            type="checkbox"
            checked={value.parking}
            onChange={(e) => set("parking", e.target.checked)}
          />
          Parking
        </label>
        <label className="pf-check">
          <input
            type="checkbox"
            checked={value.pets}
            onChange={(e) => set("pets", e.target.checked)}
          />
          Pets
        </label>
      </div>
    </fieldset>
  );
}
