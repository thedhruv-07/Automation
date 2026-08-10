import { useEffect, useRef, useState } from "react";

export default function MultiSelectDropdown({
  options, selected, onChange, label, ariaLabel,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const filteredOptions = options.filter((o) =>
    o.toLowerCase().includes(search.toLowerCase())
  );

  function toggle(option) {
    if (selected.includes(option)) {
      onChange(selected.filter((s) => s !== option));
    } else {
      onChange([...selected, option]);
    }
  }

  const buttonLabel = selected.length === 0 ? label : `${selected.length} selected`;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={ariaLabel}
        aria-expanded={open}
        className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary text-left focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        {buttonLabel}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-64 bg-surface border border-line rounded-lg shadow-lg p-2">
          <div className="flex items-center justify-between gap-2 mb-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              aria-label={`Search ${ariaLabel}`}
              className="flex-1 bg-surface-page border border-line rounded-lg px-2 py-1 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs font-semibold text-accent hover:underline whitespace-nowrap"
              >
                Clear
              </button>
            )}
          </div>
          <div className="max-h-56 overflow-y-auto space-y-1">
            {filteredOptions.length === 0 && (
              <p className="text-sm text-ink-secondary px-1 py-1">No matches</p>
            )}
            {filteredOptions.map((option) => (
              <label
                key={option}
                className="flex items-center gap-2 px-1 py-1 text-sm text-ink-primary hover:bg-surface-page rounded cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => toggle(option)}
                />
                {option}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
