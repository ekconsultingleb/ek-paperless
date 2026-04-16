# modules/constants.py
# ─────────────────────────────────────────────────────────────────────────────
# Single source of truth for all page routing keys and app-wide config.
# Import this wherever you reference a page name or config value.
# Never type these strings manually in app.py — always use these constants.
# ─────────────────────────────────────────────────────────────────────────────

# ── Page routing keys ─────────────────────────────────────────────────────────
PAGE_HOME           = "home"
PAGE_CASH           = "cash"
PAGE_INVENTORY      = "inventory"
PAGE_WASTE          = "waste"
PAGE_INVOICES       = "invoices"
PAGE_TRANSFERS      = "transfers"
PAGE_DASHBOARD      = "dashboard"
PAGE_LEDGER         = "ledger"
PAGE_OVERVIEW       = "overview"
PAGE_RECIPES        = "recipes"
PAGE_RECIPES_REPORT = "recipes report"
PAGE_PRICING_STUDIO = "pricing studio"
PAGE_MAIN           = "main"

# ── Module access keys (must match values stored in users.module column) ──────
MOD_CASH           = "cash"
MOD_INVENTORY      = "inventory"
MOD_WASTE          = "waste"
MOD_INVOICES       = "invoices"
MOD_TRANSFERS      = "transfers"
MOD_DASHBOARD      = "dashboard"
MOD_LEDGER         = "ledger"
MOD_OVERVIEW       = "overview"
MOD_RECIPES        = "recipes"
MOD_RECIPES_REPORT = "recipes report"
MOD_PRICING_STUDIO = "pricing studio"

# Full module list for admin/admin_all roles
ALL_MODULES = [
    MOD_DASHBOARD,
    MOD_CASH,
    MOD_INVENTORY,
    MOD_WASTE,
    MOD_TRANSFERS,
    MOD_INVOICES,
    MOD_LEDGER,
    MOD_OVERVIEW,
    MOD_RECIPES,
    MOD_RECIPES_REPORT,
    MOD_PRICING_STUDIO,
]

# ── App config ────────────────────────────────────────────────────────────────
LOGO_URL    = "https://hgvubaohmgvesblfvdps.supabase.co/storage/v1/object/public/assets/EK-Logo.png"
APP_VERSION = "2.2.5"
