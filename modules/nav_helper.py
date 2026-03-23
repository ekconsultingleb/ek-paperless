import streamlit as st
import pandas as pd
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# CORE DATA FETCHERS — single source of truth: clients / branches / areas
# ══════════════════════════════════════════════════════════════════════════════

def get_all_clients() -> list:
    """All active client names from clients table."""
    try:
        res = get_supabase().table("clients").select("client_name").order("client_name").execute()
        return [r["client_name"] for r in (res.data or []) if r.get("client_name")]
    except Exception:
        return []


def get_outlets_for_client(client_name: str) -> list:
    """
    All outlet codes from branches table for a given client.
    If client_name is 'All' or empty → return all outlets across all clients.
    """
    try:
        q = get_supabase().table("branches").select("outlet").order("outlet")
        if str(client_name).strip().lower() not in ["all", "", "none", "nan"]:
            q = q.eq("client_name", client_name)
        res = q.execute()
        return [r["outlet"] for r in (res.data or []) if r.get("outlet")]
    except Exception:
        return []


def get_areas_for_outlet(outlet: str) -> list:
    """
    All area names from areas table for a given outlet.
    If outlet is 'All' or empty → return all areas across all outlets.
    """
    try:
        q = get_supabase().table("areas").select("area_name").order("area_name")
        if str(outlet).strip().lower() not in ["all", "", "none", "nan"]:
            q = q.eq("outlet", outlet)
        res = q.execute()
        return [r["area_name"] for r in (res.data or []) if r.get("area_name")]
    except Exception:
        return []


def get_client_for_outlet(outlet: str) -> str:
    """Reverse lookup — given an outlet code, return its client_name."""
    try:
        res = get_supabase().table("branches").select("client_name").eq("outlet", outlet).limit(1).execute()
        if res.data:
            return res.data[0]["client_name"]
    except Exception:
        pass
    return "All"


# ══════════════════════════════════════════════════════════════════════════════
# get_nav_data — kept for backward compatibility with dashboard.py and any
# module that calls it directly. Now reads from branches + areas instead of
# users + master_items.
# ══════════════════════════════════════════════════════════════════════════════

def get_nav_data(client_name: str) -> pd.DataFrame:
    """
    Returns a deduplicated DataFrame of (client_name, outlet, location)
    sourced from branches + areas tables.

    Drop-in replacement for the old users/master_items version.
    All callers (dashboard, etc.) continue to work unchanged.
    """
    try:
        # Fetch branches
        q_br = get_supabase().table("branches").select("client_name, outlet")
        if str(client_name).strip().lower() not in ["all", "", "none", "nan"]:
            q_br = q_br.eq("client_name", client_name)
        br_res = q_br.execute()
        branches = br_res.data or []

        if not branches:
            return pd.DataFrame(columns=["client_name", "outlet", "location"])

        # For each branch, fetch its areas
        rows = []
        outlet_list = [b["outlet"] for b in branches]

        q_ar = get_supabase().table("areas").select("outlet, area_name")
        if outlet_list:
            # Supabase supports .in_() for list filtering
            q_ar = q_ar.in_("outlet", outlet_list)
        ar_res = q_ar.execute()
        areas = ar_res.data or []

        # Build area lookup
        area_map: dict[str, list] = {}
        for a in areas:
            area_map.setdefault(a["outlet"], []).append(a["area_name"])

        for b in branches:
            outlet     = b["outlet"]
            cname      = b["client_name"]
            locs       = area_map.get(outlet, [])
            if locs:
                for loc in locs:
                    rows.append({"client_name": cname, "outlet": outlet, "location": loc})
            else:
                # Branch exists but has no areas yet — include with empty location
                rows.append({"client_name": cname, "outlet": outlet, "location": ""})

        df = pd.DataFrame(rows)
        df["client_name"] = df["client_name"].astype(str).str.strip()
        df["outlet"]      = df["outlet"].astype(str).str.strip()
        df["location"]    = df["location"].astype(str).str.strip()
        df = df[df["location"] != ""]
        return df.drop_duplicates().reset_index(drop=True)

    except Exception:
        return pd.DataFrame(columns=["client_name", "outlet", "location"])


# ══════════════════════════════════════════════════════════════════════════════
# build_outlet_location_sidebar
# ══════════════════════════════════════════════════════════════════════════════

def build_outlet_location_sidebar(assigned_client, assigned_outlet, assigned_location,
                                   outlet_key="nav_outlet", location_key="nav_location"):
    """
    Renders Branch / Outlet / Location selectors in the sidebar.
    Returns (final_client, final_outlet, final_location) as clean strings.

    Logic per field:
    ┌─────────────────┬──────────────────────────────────────────────────────┐
    │ users value     │ behaviour                                            │
    ├─────────────────┼──────────────────────────────────────────────────────┤
    │ "All"           │ dropdown from 3 tables (full list)                   │
    │ specific value  │ locked label — no dropdown, value passed through     │
    └─────────────────┴──────────────────────────────────────────────────────┘

    Source of dropdown values is ALWAYS clients / branches / areas.
    """
    clean_client   = str(assigned_client).strip()
    clean_outlet   = str(assigned_outlet).strip()
    clean_location = str(assigned_location).strip()

    is_all_client   = clean_client.lower()   in ["all", "", "none", "nan"]
    is_all_outlet   = clean_outlet.lower()   in ["all", "", "none", "nan"]
    is_all_location = clean_location.lower() in ["all", "", "none", "nan"]

    st.sidebar.markdown("### 📍 Location Details")

    # ── CLIENT ────────────────────────────────────────────────────────────────
    if not is_all_client:
        # Specific client assigned — locked
        final_client = clean_client
        st.sidebar.markdown(f"**🏢 Client:** {final_client}")
    else:
        # EK team / admin — show all clients from clients table
        c_list = get_all_clients()
        if c_list:
            final_client = st.sidebar.selectbox(
                "🏢 Select Client", c_list, key=f"{outlet_key}_client")
        else:
            final_client = "All"
            st.sidebar.markdown("**🏢 Client:** All")

    # ── OUTLET ────────────────────────────────────────────────────────────────
    if not is_all_outlet:
        # Specific outlet assigned — locked
        final_outlet = clean_outlet
        st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
    else:
        # Show outlets from branches filtered by selected client
        outlet_list = get_outlets_for_client(final_client)
        if outlet_list:
            final_outlet = st.sidebar.selectbox(
                "🏠 Select Outlet", outlet_list, key=outlet_key)
        else:
            final_outlet = "None"
            st.sidebar.warning("⚠️ No outlets found for this client.")

    # ── AREA / LOCATION ───────────────────────────────────────────────────────
    if not is_all_location:
        # User has specific area(s) assigned — parse comma-separated list
        assigned_areas = [l.strip() for l in clean_location.split(",") if l.strip()]

        # Get valid areas for this outlet from areas table
        db_areas = get_areas_for_outlet(final_outlet)

        # Intersect assigned with what exists in DB
        valid_areas = [a for a in assigned_areas if a in db_areas]
        if not valid_areas:
            # Assigned areas not in DB yet — trust the assignment, show warning
            valid_areas = assigned_areas
            st.sidebar.warning(
                f"⚠️ Assigned area(s) not found in DB: {', '.join(assigned_areas)}")

        if len(valid_areas) > 1:
            final_location = st.sidebar.selectbox(
                "📍 Select Area", valid_areas, key=location_key)
        else:
            final_location = valid_areas[0]
            st.sidebar.markdown(f"**📍 Area:** {final_location}")
    else:
        # User has All — show all areas for selected outlet from areas table
        area_list = get_areas_for_outlet(final_outlet)

        if len(area_list) > 1:
            final_location = st.sidebar.selectbox(
                "📍 Select Area", area_list, key=location_key)
        elif len(area_list) == 1:
            final_location = area_list[0]
            st.sidebar.markdown(f"**📍 Area:** {final_location}")
        else:
            final_location = "All"
            st.sidebar.markdown("**📍 Area:** All")

    return final_client, final_outlet, final_location