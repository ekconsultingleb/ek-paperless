import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- THE CUMULATIVE COUNTING LOGIC ---
def add_inventory_qty(item_key, row_dict, input_key):
    added_val = st.session_state[input_key]
    
    if added_val > 0:
        if item_key not in st.session_state['mobile_counts']:
            st.session_state['mobile_counts'][item_key] = {
                'row_data': row_dict,
                'qty': 0.0
            }
        
        st.session_state['mobile_counts'][item_key]['qty'] += added_val
        st.session_state[input_key] = 0.0

def undo_inventory_count(item_key):
    if item_key in st.session_state['mobile_counts']:
        del st.session_state['mobile_counts'][item_key]

def render_inventory(conn, sheet, user, role, outlet, location):
    st.markdown("## Inventory Count")
    
    supabase = get_supabase()

    if 'mobile_counts' not in st.session_state:
        st.session_state['mobile_counts'] = {}

    try:
        response = supabase.table("master_items").select("*").execute()
        if not response.data:
            st.warning("⚠️ No items found in the master list.")
            return
        df_items = pd.DataFrame(response.data)
        df_items.columns = [c.lower() for c in df_items.columns]
    except Exception as e:
        st.error(f"Failed to load master items: {e}")
        return

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

    df_client_items = df_items[df_items['client_name'] == selected_client].copy()
    if outlet.lower() != "all":
        df_client_items = df_client_items[df_client_items['outlet'] == outlet]
    
    if 'item_type' in df_client_items.columns:
        df_client_items = df_client_items[df_client_items['item_type'].astype(str).str.lower() == 'inventory']

    if df_client_items.empty:
        st.warning("No inventory items found for this location.")
        return

    st.divider()

    # --- 3. MISSING ITEM FEATURE ---
    with st.expander("➕ Missing an item? Add it manually here"):
        c_name = st.text_input("Item Name (e.g., Redbull)")
        col_cat, col_grp = st.columns(2)
        with col_cat:
            cat_options = list(df_client_items['category'].dropna().unique())
            c_cat = st.selectbox("Category", cat_options, key="custom_cat")
        with col_grp:
            grp_options = list(df_client_items[df_client_items['category'] == c_cat]['sub_category'].dropna().unique())
            c_grp = st.selectbox("Sub Category", grp_options, key="custom_grp")
            
        col_qty, col_unit = st.columns(2)
        with col_qty:
            c_qty = st.number_input("Quantity", min_value=0.0, step=1.0, format="%g", key="custom_qty")
        with col_unit:
            c_unit = st.text_input("Unit (e.g., Can, Kg)")
            
        if st.button("Save Custom Item", use_container_width=True):
            if c_name and c_qty > 0:
                fake_row = {
                    "item_name": c_name.upper(), "category": c_cat, 
                    "sub_category": c_grp, "count_unit": c_unit.title() if c_unit else "Pcs"
                }
                st.session_state['mobile_counts'][f"CUSTOM_{c_name}"] = {'row_data': fake_row, 'qty': c_qty}
                st.success(f"Added {c_name} to cart!")
                st.rerun()

    # --- 4. SMART FILTERS & SEARCH ---
    st.subheader("🔍 Filter & Count")
    
    search_query = st.text_input("🔍 Quick Search", placeholder="Search any item (Overrides filters below)...")
    
    c1, c2 = st.columns(2)
    with c1:
        cats = sorted(list(df_client_items['category'].dropna().astype(str).unique()))
        cat_options = ["All"] + cats
        selected_category = st.selectbox("📂 Category", cat_options, index=1 if cats else 0)
    with c2:
        df_grp_list = df_client_items if selected_category == "All" else df_client_items[df_client_items['category'] == selected_category]
        grps = sorted(list(df_grp_list['sub_category'].dropna().astype(str).unique()))
        grp_options = ["All"] + grps
        selected_group = st.selectbox("🏷️ Sub Category", grp_options, index=1 if grps else 0)

    if search_query:
        df_display = df_client_items[df_client_items['item_name'].str.contains(search_query, case=False, na=False)].copy()
    else:
        df_display = df_client_items.copy()
        if selected_category != "All":
            df_display = df_display[df_display['category'] == selected_category]
        if selected_group != "All":
            df_display = df_display[df_display['sub_category'] == selected_group]

    # --- 🟢 LIVE PROGRESS BADGES ---
    total_items = len(df_display)
    counted_in_view = sum(1 for item in df_display['item_name'] if item in st.session_state['mobile_counts'])
    
    st.markdown(f"""
        <div style='display: flex; justify-content: space-between; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
            <span style='color: #00ff00;'>✅ {counted_in_view} Counted</span>
            <span style='color: white;'>📝 {total_items} Items in {selected_group}</span>
        </div>
    """, unsafe_allow_html=True)

    # --- 5. THE LIVE ENTRY LIST ---
    if df_display.empty:
        st.info("No items found.")
    else:
        for index, row in df_display.iterrows():
            item_name = row['item_name']
            
            cart_data = st.session_state['mobile_counts'].get(item_name)
            current_total = cart_data['qty'] if cart_data else 0.0
            
            with st.container(border=True):
                if current_total > 0:
                    st.markdown(f"🟢 **{item_name}** &nbsp;|&nbsp; ✅ Total: **{current_total}**")
                else:
                    st.markdown(f"🔴 **{item_name}** &nbsp;|&nbsp; 📦 {row.get('count_unit', 'pcs')}")
                
                col_add, col_btn = st.columns([3, 1], vertical_alignment="center")
                input_key = f"inv_add_{row.get('id', index)}"
                
                with col_add:
                    st.number_input(
                        "+ Add Qty", 
                        value=0.0, 
                        min_value=0.0, 
                        step=1.0, 
                        format="%g", 
                        key=input_key,
                        on_change=add_inventory_qty,
                        args=(item_name, row.to_dict(), input_key),
                        label_visibility="collapsed",
                        placeholder="Type amount and press Enter"
                    )
                with col_btn:
                    if current_total > 0:
                        if st.button("🗑️ Undo", key=f"undo_{row.get('id', index)}"):
                            undo_inventory_count(item_name)
                            st.rerun()

    # --- 🛒 REVIEW & SUBMIT TO CLOUD ---
    st.divider()
    cart_size = len(st.session_state['mobile_counts'])
    if cart_size > 0:
        st.success(f"🛒 **{cart_size} items** ready to submit.")
        with st.expander("👀 Review & Submit Count", expanded=True):
            
            preview_list = []
            for k, v in st.session_state['mobile_counts'].items():
                preview_list.append({
                    "Item": v['row_data'].get('item_name', k),
                    "Total Counted": v['qty'],
                    "Unit": v['row_data'].get('count_unit', '')
                })
            st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)

            if st.button("🚀 SUBMIT ALL COUNTS TO CLOUD", type="primary", use_container_width=True):
                logs = []
                for i_name, data in st.session_state['mobile_counts'].items():
                    r_data = data['row_data']
                    logs.append({
                        "date": str(count_date),
                        "client_name": selected_client,
                        "outlet": outlet,
                        "location": selected_location,
                        "counted_by": user,
                        
                        "item_name": r_data.get('item_name', i_name),
                        "product_code": r_data.get('product_code', ''),
                        "item_type": r_data.get('item_type', ''),
                        "category": r_data.get('category', ''),
                        "sub_category": r_data.get('sub_category', ''),
                        
                        "quantity": float(data['qty']),
                        "count_unit": r_data.get('count_unit', 'pcs')
                    })
                
                if logs:
                    try:
                        supabase.table("inventory_logs").insert(logs).execute()
                        st.success("✅ Saved to Cloud!")
                        st.session_state['mobile_counts'] = {}
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")