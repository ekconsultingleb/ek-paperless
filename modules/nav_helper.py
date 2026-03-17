import streamlit as st
import pandas as pd
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def get_nav_data(client_name: str) -> pd.DataFrame:
    """
    Returns a deduplicated DataFrame of (client_name, outlet, location)
    for building sidebar navigation dropdowns.

    Strategy:
    1. Query users table filtered by client_name — fast, tiny result.
       Extract rows where outlet != 'All' to get real assignments.
    2. If nothing found (all users have outlet=All, e.g. Paperless test users),
       fall back to paginated master_items fetch to discover real outlets/locations.

    Returns columns: client_name, outlet, location
    """
    supabase = get_supabase()

    # ── Step 1: try users table ──────────────────────────────────────────────
    try:
        query = supabase.table("users").select("client_name, outlet, location")
        if str(client_name).strip().lower() not in ['all', '', 'none']:
            query = query.eq("client_name", client_name)
        res = query.execute()

        if res.data:
            df = pd.DataFrame(res.data)
            df['client_name'] = df['client_name'].astype(str).str.strip().str.title()
            df['outlet']      = df['outlet'].astype(str).str.strip().str.title()
            df['location']    = df['location'].astype(str).str.strip()

            # Keep only rows with real outlet values (not All/nan/empty)
            df_real = df[~df['outlet'].str.lower().isin(['all', 'nan', 'none', ''])]

            if not df_real.empty:
                # Explode comma-separated locations into individual rows
                df_real = df_real.copy()
                df_real['location'] = df_real['location'].str.split(',')
                df_real = df_real.explode('location')
                df_real['location'] = df_real['location'].str.strip().str.title()
                df_real = df_real[~df_real['location'].str.lower().isin(['all', 'nan', 'none', ''])]
                return df_real[['client_name', 'outlet', 'location']].drop_duplicates().reset_index(drop=True)
    except Exception:
        pass

    # ── Step 2: fallback — paginated master_items fetch ──────────────────────
    try:
        all_rows = []
        page_size, start_row = 1000, 0
        while True:
            q = supabase.table("master_items").select("client_name, outlet, location")
            if str(client_name).strip().lower() not in ['all', '', 'none']:
                q = q.ilike("client_name", f"%{client_name}%")
            res = q.range(start_row, start_row + page_size - 1).execute()
            if not res.data:
                break
            all_rows.extend(res.data)
            if len(res.data) < page_size:
                break
            start_row += page_size

        if all_rows:
            df = pd.DataFrame(all_rows)
            df['client_name'] = df['client_name'].astype(str).str.strip().str.title()
            df['outlet']      = df['outlet'].astype(str).str.strip().str.title()
            df['location']    = df['location'].astype(str).str.strip().str.title()
            df = df[~df['outlet'].str.lower().isin(['all', 'nan', 'none', ''])]
            df = df[~df['location'].str.lower().isin(['all', 'nan', 'none', ''])]
            return df[['client_name', 'outlet', 'location']].drop_duplicates().reset_index(drop=True)
    except Exception:
        pass

    return pd.DataFrame(columns=['client_name', 'outlet', 'location'])


def build_outlet_location_sidebar(assigned_client, assigned_outlet, assigned_location,
                                   outlet_key="nav_outlet", location_key="nav_location"):
    """
    Renders Branch / Outlet / Location selectors in the sidebar.
    Returns (final_client, final_outlet, final_location) as clean strings.

    - If the user has a specific value assigned → show it as a label (no dropdown)
    - If the user has 'All' → show a dropdown built from real data
    """
    supabase = get_supabase()

    clean_client   = str(assigned_client).strip().title()
    clean_outlet   = str(assigned_outlet).strip().title()
    clean_location = str(assigned_location).strip()

    st.sidebar.markdown("### 📍 Location Details")

    # ── CLIENT ───────────────────────────────────────────────────────────────
    if clean_client.lower() not in ['all', '', 'none', 'nan']:
        final_client = clean_client
        st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
    else:
        df_nav = get_nav_data("all")
        c_list = sorted(df_nav['client_name'].unique().tolist()) if not df_nav.empty else []
        if c_list:
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list, key=f"{outlet_key}_client")
        else:
            final_client = "All"
            st.sidebar.markdown("**🏢 Branch:** All")

    # ── OUTLET ───────────────────────────────────────────────────────────────
    if clean_outlet.lower() not in ['all', '', 'none', 'nan']:
        final_outlet = clean_outlet
        st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
    else:
        df_nav = get_nav_data(final_client)
        if final_client.lower() not in ['all', '', 'none']:
            outlet_list = sorted(df_nav[df_nav['client_name'] == final_client]['outlet'].unique().tolist()) if not df_nav.empty else []
        else:
            outlet_list = sorted(df_nav['outlet'].unique().tolist()) if not df_nav.empty else []

        if outlet_list:
            final_outlet = st.sidebar.selectbox("🏠 Select Outlet", outlet_list, key=outlet_key)
        else:
            final_outlet = "None"
            st.sidebar.warning("⚠️ No outlets found for this client.")

    # ── LOCATION ─────────────────────────────────────────────────────────────
    # Determine allowed locations based on assignment
    allowed_locs_raw = [l.strip().title() for l in clean_location.split(',') if l.strip()] \
                       if clean_location.lower() not in ['all', '', 'none', 'nan'] else []

    # Get locations that exist in the DB for this outlet
    df_nav = get_nav_data(final_client)
    if not df_nav.empty and final_outlet not in ['None', 'All', '']:
        db_locs = sorted(df_nav[df_nav['outlet'] == final_outlet]['location'].unique().tolist())
    elif not df_nav.empty:
        db_locs = sorted(df_nav['location'].unique().tolist())
    else:
        db_locs = []

    if allowed_locs_raw:
        # User has specific locations — intersect with DB, show only valid ones
        valid_locs = [l for l in allowed_locs_raw if l in db_locs]
        if not valid_locs:
            valid_locs = allowed_locs_raw  # show assigned even if not in DB yet
            st.sidebar.warning(f"⚠️ Assigned locations not in DB: {', '.join(allowed_locs_raw)}")
    else:
        # User has All — show everything from DB
        valid_locs = db_locs

    if len(valid_locs) > 1:
        final_location = st.sidebar.selectbox("📍 Select Location", valid_locs, key=location_key)
    elif len(valid_locs) == 1:
        final_location = valid_locs[0]
        st.sidebar.markdown(f"**📍 Location:** {final_location}")
    else:
        final_location = "All"
        st.sidebar.markdown("**📍 Location:** All")

    return final_client, final_outlet, final_location