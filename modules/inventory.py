import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_inventory(conn, sheet, user, role, outlet, location):
    st.markdown("##   Inventory Count")
    
    supabase = get_supabase()

    # --- 1. FETCH MASTER ITEMS ---
    try:
        response = supabase.table("master_items").select("*").execute()
        if not response.data:
            st.warning("⚠️ No items found in the master list.")
            return
        df_items = pd.DataFrame(response.data)
        
        # KEY FIX: Force column names to lowercase to avoid 'Unit' vs 'unit' errors
        df_items.columns = [c.lower() for c in df_items.columns]
        
    except Exception as e:
        st.error(f"Failed to load master items: {e}")
        return

    # --- 2. TOP SETTINGS ---
    col1, col2, col3 = st.columns(3)
    with col1:
        clients = df_items['client_name'].dropna().unique()
        selected_client = st.selectbox("🏢 Client", clients)
    with col2:
        count_date = st.date_input("📅 Date", date.today())
    with col3:
        locations = ["MED", "WAREHOUSE", "CHALET", "BAR"]
        if str(location).lower() != "all":
            selected_location = st.selectbox("📍 Location", [location], disabled=True)
        else:
            selected_location = st.selectbox("📍 Location", locations)

    # Filter items for this client AND Outlet (to make sure La Siesta only sees La Siesta)
    df_client_items = df_items[df_items['client_name'] == selected_client].copy()
    if outlet.lower() != "all":
        df_client_items = df_client_items[df_client_items['outlet'] == outlet]
    df_client_items = df_client_items[df_client_items['item_type'].astype(str).str.lower() == 'inventory']

    if df_client_items.empty:
        st.warning("No items found for this client and outlet.")
        return

    st.divider()

    # --- SESSION STATES ---
    if 'mobile_counts' not in st.session_state:
        st.session_state['mobile_counts'] = {}
    if 'custom_items' not in st.session_state:
        st.session_state['custom_items'] = []

    # --- 3. MISSING ITEM FEATURE ---
    with st.expander("➕ Missing an item? Add it manually here"):
        c_name = st.text_input("Item Name (e.g., Redbull)")
        col_cat, col_grp = st.columns(2)
        with col_cat:
            cat_options = list(df_client_items['category'].dropna().unique())
            c_cat = st.selectbox("Category", cat_options, key="custom_cat")
        with col_grp:
            # FIXED: 'sub_category'
            grp_options = list(df_client_items[df_client_items['category'] == c_cat]['sub_category'].dropna().unique())
            c_grp = st.selectbox("Sub Category", grp_options, key="custom_grp")
            
        col_qty, col_unit = st.columns(2)
        with col_qty:
            c_qty = st.number_input("Quantity", min_value=0.0, key="custom_qty")
        with col_unit:
            c_unit = st.text_input("Unit (e.g., Can, Kg)")
            
        if st.button("Save Custom Item", use_container_width=True):
            if c_name and c_qty >= 0:
                st.session_state['custom_items'].append({
                    "item_name": c_name.upper(),
                    "category": c_cat,
                    "sub_category": c_grp, # FIXED
                    "quantity": c_qty,
                    "count_unit": c_unit.title() if c_unit else "Pcs" # FIXED
                })
                st.success(f"Added {c_name} to session!")

    # --- 4. FILTERS & SEARCH ---
    search_query = st.text_input("🔍 Search Item...", placeholder="e.g. Tomato...")
    c1, c2 = st.columns(2)
    with c1:
        categories = list(df_client_items['category'].dropna().unique())
        selected_category = st.selectbox("📂 Category", categories)
    with c2:
        # FIXED: 'sub_category'
        groups = list(df_client_items[df_client_items['category'] == selected_category]['sub_category'].dropna().unique())
        selected_group = st.selectbox("🏷️ Group", groups)

    df_display = df_client_items[
        (df_client_items['category'] == selected_category) & 
        (df_client_items['sub_category'] == selected_group)
    ].copy()
    
    if search_query:
        df_display = df_display[df_display['item_name'].str.contains(search_query, case=False, na=False)]

    # --- PROGRESS BADGES ---
    total_items = len(df_display)
    counted_items = sum(1 for item in df_display['item_name'] if st.session_state['mobile_counts'].get(item) is not None)
    
    st.markdown(f"""
        <div style='display: flex; justify-content: space-between; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
            <span style='color: white;'>✅ {counted_items} Counted</span>
            <span style='color: white;'>❌ {total_items - counted_items} Pending</span>
        </div>
    """, unsafe_allow_html=True)

    # --- 5. THE FORM ---
    with st.form("mobile_inventory_form"):
        if df_display.empty:
            st.info("No items found.")
        else:
            for index, row in df_display.iterrows():
                item_name = row['item_name']
                is_counted = st.session_state['mobile_counts'].get(item_name) is not None
                status_emoji = "🟢" if is_counted else "🔴"
                
                col_name, col_input = st.columns([6, 4])
                with col_name:
                    st.markdown(f"**{status_emoji} {item_name}**")
                    # FIXED: 'count_unit'
                    st.caption(f"Unit: {row.get('count_unit', 'pcs')}")
                
                with col_input:
                    current_val = st.session_state['mobile_counts'].get(item_name)
                    val = st.number_input(
                        "Qty", 
                        value=float(current_val) if current_val is not None else 0.0,
                        min_value=0.0, 
                        key=f"input_{row.get('id', index)}", # Safety check for ID
                        label_visibility="collapsed"
                    )
                    if val > 0 or current_val is not None:
                        st.session_state['mobile_counts'][item_name] = val
        
        submit_btn = st.form_submit_button("🚀 SUBMIT ALL COUNTS TO CLOUD", use_container_width=True)
        
        if submit_btn:
            logs = []
            # Standard Items
            for i_name, qty in st.session_state['mobile_counts'].items():
                item_info = df_client_items[df_client_items['item_name'] == i_name].iloc[0]
                logs.append({
                    "date": str(count_date),
                    "client_name": selected_client,
                    "outlet": outlet, # <-- Added this
                    "location": selected_location,
                    "counted_by": user,
                    
                    "item_name": i_name,
                    "product_code": item_info.get('product_code', ''), # <-- Added this
                    "item_type": item_info.get('item_type', ''),       # <-- Added this
                    "category": item_info.get('category', ''),
                    "sub_category": item_info.get('sub_category', ''),
                    
                    "quantity": float(qty),
                    "count_unit": item_info.get('count_unit', 'pcs')
                })
            # Custom Items
            for c in st.session_state['custom_items']:
                logs.append({
                    "client_name": selected_client, "date": str(count_date), "location": selected_location,
                    "item_name": f"⚠️ {c['item_name']}", "category": c['category'], "sub_category": c['sub_category'], # FIXED
                    "quantity": float(c['quantity']), "count_unit": c['count_unit'], "counted_by": user # FIXED
                })
            
            if logs:
                try:
                    supabase.table("inventory_logs").insert(logs).execute()
                    st.success("✅ Saved to Cloud!")
                    st.session_state['mobile_counts'] = {}
                    st.session_state['custom_items'] = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")