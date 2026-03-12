"use client";

type AnyObj = Record<string, unknown>;

function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function displayValue(v: unknown): string {
  if (v === null || v === undefined) return "-";
  if (Array.isArray(v)) return v.map((x) => String(x)).join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function RenderedCompanyView({ data }: { data: AnyObj }) {
  const companyJson = (data.company_json && typeof data.company_json === "object" ? data.company_json : {}) as AnyObj;
  const allEntries = Object.entries(companyJson);

  const heroKeys = [
    "name",
    "short_name",
    "category",
    "incorporation_year",
    "nature_of_company",
    "headquarters_address",
  ];

  const hero = heroKeys
    .filter((k) => k in companyJson)
    .map((k) => [k, companyJson[k]] as const);

  const rest = allEntries.filter(([k]) => !heroKeys.includes(k));

  return (
    <div className="space-y-4">
      <section className="card border-slate-300 bg-gradient-to-br from-white to-slate-100">
        <h3 className="text-lg font-semibold">{displayValue(companyJson.name) || "Company Details"}</h3>
        <p className="mt-1 text-sm text-slate-600">
          {displayValue(companyJson.overview_text)}
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {hero.map(([k, v]) => (
            <div key={k} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-slate-500">{humanize(k)}</p>
              <p className="mt-1 text-sm font-medium text-slate-900">{displayValue(v)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h4 className="mb-3 font-semibold">Rendered Fields</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          {rest.map(([k, v]) => (
            <article key={k} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-slate-500">{humanize(k)}</p>
              <p className="mt-1 text-sm text-slate-900 whitespace-pre-wrap break-words">{displayValue(v)}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

