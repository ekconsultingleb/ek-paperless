import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_waste(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown("### 🗑️ Daily Waste & Events")
    supabase = get_supabase()
    
    try:
        # 1. GET ALL OUTLETS FOR SIDEBAR
        nav_res = supabase.table("master_items").select("outlet, client_name").execute()
        df_nav = pd.DataFrame(nav_res.data)
        client_filter = st.sidebar.selectbox("🏢 Client", sorted(df_nav['client_name'].unique()))
        outlet_options = sorted(df_nav[df_nav['client_name'] == client_filter]['outlet'].unique())
        final_outlet = assigned_outlet if assigned_outlet.lower() != 'all' else st.sidebar.selectbox("🏠 Outlet", outlet_options)

        # 2. 🚨 THE "MEGA-FETCH" LOOP 🚨
        # This is how we get past the 1,000 row wall to reach Row 2,000+
        all_items = []
        page_size = 1000
        start_row = 0
        
        while True:
            res = supabase.table("master_items").select("*").eq("outlet", final_outlet).range(start_row, start_row + page_size - 1).execute()
            if not res.data:
                break
            all_items.extend(res.data)
            if len(res.data) < page_size: # We hit the end of the list
                break
            start_row += page_size

        df_items = pd.DataFrame(all_items)
        df_items.columns = [c.lower() for c in df_items.columns]

        # 3. VERIFY & FILTER
        st.info(f"📊 System Status: Successfully bypassed 1,000-row limit. Loaded **{len(df_items)}** total items for {final_outlet}.")

        # Main Filters
        search_query = st.text_input("🔍 Search Item Name...", placeholder="e.g. Burger, Arak Glass...")
        col1, col2 = st.columns(2)
        with col1:
            cats = sorted(df_items['category'].dropna().unique())
            cat_filter = st.selectbox("📂 Category", ["All"] + cats)
        with col2:
            df_sub = df_items if cat_filter == "All" else df_items[df_items['category'] == cat_filter]
            sub_filter = st.selectbox("🏷️ Sub Category", ["All"] + sorted(df_sub['sub_category'].dropna().unique()))

        # Final Logic
        if search_query:
            filtered_df = df_items[df_items['item_name'].str.contains(search_query, case=False, na=False)]
        else:
            filtered_df = df_items.copy()
            if cat_filter != "All": filtered_df = filtered_df[filtered_df['category'] == cat_filter]
            if sub_filter != "All": filtered_df = filtered_df[filtered_df['sub_category'] == sub_filter]

        # 4. RENDER CARDS
        if filtered_df.empty:
            st.warning("No items found matching these filters.")
        else:
            for idx, row in filtered_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['item_name']}** | {row.get('count_unit', 'pcs')}")
                    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="bottom")
                    q_val = c1.number_input("Qty", 0.0, step=1.0, key=f"q_{idx}")
                    rem = c2.text_input("Reason", key=f"r_{idx}")
                    if c3.button("Add", key=f"b_{idx}", use_container_width=True):
                        # Submission logic here...
                        st.success("Added to list!")

    except Exception as e:
        st.error(f"Error: {e}")