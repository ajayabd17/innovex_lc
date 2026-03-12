"use client";

import Link from "next/link";

type NavItem = {
  href: string;
  label: string;
  active?: boolean;
  disabled?: boolean;
};

export function PageNav({ items }: { items: NavItem[] }) {
  return (
    <div className="card py-2">
      <nav className="flex flex-wrap items-center gap-2">
        {items.map((item) => (
          <Link
            key={`${item.href}-${item.label}`}
            href={item.disabled ? "#" : item.href}
            aria-disabled={item.disabled}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              item.disabled
                ? "pointer-events-none bg-slate-100 text-slate-400"
                : item.active
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

