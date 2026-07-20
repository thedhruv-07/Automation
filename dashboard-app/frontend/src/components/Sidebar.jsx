const ICONS = {
  dashboard: (
    <path d="M3 3h8v8H3V3zm10 0h8v5h-8V3zM3 13h8v8H3v-8zm10 3h8v5h-8v-5z" />
  ),
  clients: (
    <path d="M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H5z" />
  ),
  sync: (
    <path d="M17 2l4 4-4 4M3 12a9 9 0 0115-6.7M7 22l-4-4 4-4M21 12a9 9 0 01-15 6.7" />
  ),
  whatsapp: (
    <path d="M12 2a10 10 0 00-8.6 15.1L2 22l4.9-1.3A10 10 0 1012 2z" />
  ),
  log: (
    <path d="M4 6h16M4 12h16M4 18h10" />
  ),
};

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "dashboard", view: "dashboard" },
  { key: "clients", label: "Client Data", icon: "clients", view: "clientData" },
  { key: "sync", label: "Excel Sync", icon: "sync", view: "excelSync" },
  { key: "whatsapp", label: "WhatsApp Settings", icon: "whatsapp", view: "whatsappSettings" },
  { key: "log", label: "Message Log", icon: "log", view: "messageLog" },
];

function NavIcon({ name }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  );
}

export default function Sidebar({ activeView, onNavigate }) {
  return (
    <aside className="w-[240px] shrink-0 h-screen sticky top-0 bg-ink-primary text-white flex flex-col py-6">
      <div className="px-6 mb-6">
        <h1 className="text-lg font-extrabold">Absolute Veritas</h1>
        <p className="text-white/50 text-xs mt-0.5">Admin Portal</p>
      </div>
      <nav className="flex-1 space-y-1" data-testid="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const isActive = item.view === activeView;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onNavigate(item.view)}
              aria-current={isActive ? "page" : undefined}
              className={`relative w-full px-6 py-3 flex items-center gap-3 text-sm transition-colors ${
                isActive
                  ? "bg-accent/10 text-white font-semibold"
                  : "text-white/60 hover:text-white hover:bg-white/5"
              }`}
            >
              {isActive && (
                <span className="absolute left-0 top-0 h-full w-1 bg-accent" aria-hidden="true" />
              )}
              <NavIcon name={item.icon} />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
