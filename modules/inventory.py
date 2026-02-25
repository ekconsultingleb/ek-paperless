import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_inventory(conn, sheet, user, role, outlet, location):
    st.markdown("## 📱 Mobile Inventory Count")
    
    supabase = get_supabase()

    # --- 1. FETCH MASTER ITEMS ---
    try:
        response = supabase.table("master_items").select("*").execute()
        if not response.data:
            st.warning("⚠️ No items found in the master list.")
            return
        df_items = pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Failed to load master items: {e}")
        return

    # --- 2. TOP SETTINGS (Sticky-feel) ---
    col1, col2, col3 = st.columns(3)
    with col1:
        clients = df_items['client_name'].dropna().unique()
        selected_client = st.selectbox("🏢 Client", clients)
    with col2:
        count_date = st.date_input("📅 Date", date.today())
    with col3:
        locations = ["MED", "WAREHOUSE", "CHALET", "BAR"]
        if location.lower() != "all":
            selected_location = st.selectbox("📍 Location", [location], disabled=True)
        else:
            selected_location = st.selectbox("📍 Location", locations)

    # Filter items for this client
    df_client_items = df_items[df_items['client_name'] == selected_client]
    if df_client_items.empty:
        st.warning("No items found for this client.")
        return

    st.divider()

    # --- SESSION STATES FOR COUNTS & MISSING ITEMS ---
    if 'mobile_counts' not in st.session_state:
        st.session_state['mobile_counts'] = {}
    if 'custom_items' not in st.session_state:
        st.session_state['custom_items'] = []

    # --- 3. BULLETPROOF MISSING ITEM FEATURE ---
    with st.expander("➕ Missing an item? Add it manually here"):
        st.info("Log unlisted items. You must use official categories!")
        
        c_name = st.text_input("Item Name (e.g., Redbull)")
        
        # Force them to pick official categories/groups
        col_cat, col_grp = st.columns(2)
        with col_cat:
            cat_options = list(df_client_items['category'].dropna().unique())
            c_cat = st.selectbox("Category", cat_options, key="custom_cat")
        with col_grp:
            grp_options = list(df_client_items[df_client_items['category'] == c_cat]['group'].dropna().unique())
            c_grp = st.selectbox("Group", grp_options, key="custom_grp")
            
        col_qty, col_unit = st.columns(2)
        with col_qty:
            c_qty = st.number_input("Quantity", min_value=0.0, step=None, value=None, key="custom_qty")
        with col_unit:
            c_unit = st.text_input("Unit (e.g., Can, Kg)")
            
        if st.button("Save Custom Item", use_container_width=True):
            if c_name and c_qty is not None and c_unit:
                # DUPLICATE CHECKER: Check if item already exists in the master list!
                existing_items = df_client_items['item_name'].str.strip().str.lower().tolist()
                
                if c_name.strip().lower() in existing_items:
                    st.error(f"⚠️ '{c_name}' already exists in the system! Please search for it in the list below.")
                else:
                    st.session_state['custom_items'].append({
                        "item_name": c_name.upper(),
                        "category": c_cat,  # Uses the selected category!
                        "group": c_grp,     # Uses the selected group!
                        "quantity": c_qty,
                        "unit": c_unit.title()
                    })
                    st.success(f"Added {c_qty} {c_unit} of {c_name} to your count!")
            else:
                st.error("Please fill out Name, Quantity, and Unit.")

    # Show temporarily saved custom items
    if st.session_state['custom_items']:
        st.write("📝 **Custom Items added to this session:**")
        for idx, ci in enumerate(st.session_state['custom_items']):
            st.caption(f"- {ci['item_name']}: {ci['quantity']} {ci['unit']} ({ci['category']} -> {ci['group']})")

    st.divider()

    # --- 4. LIGHTWEIGHT MOBILE UI: STRICT FILTERS ---
    search_query = st.text_input("🔍 Search Item...", placeholder="e.g. Tomato, Beef...")
    
    c1, c2 = st.columns(2)
    with c1:
        categories = list(df_client_items['category'].dropna().unique())
        selected_category = st.selectbox("📂 Category", categories)
    
    with c2:
        groups = list(df_client_items[df_client_items['category'] == selected_category]['group'].dropna().unique())
        selected_group = st.selectbox("🏷️ Group", groups)

    # Apply Strict Filters
    df_display = df_client_items[
        (df_client_items['category'] == selected_category) & 
        (df_client_items['group'] == selected_group)
    ].copy()
    
    if search_query:
        df_display = df_display[df_display['item_name'].str.contains(search_query, case=False, na=False)]

    # --- PROGRESS BADGES (Red vs Green) ---
    total_items = len(df_display)
    counted_items = sum(1 for item in df_display['item_name'] if st.session_state['mobile_counts'].get(item, None) is not None)
    
    st.markdown(f"""
        <div style='display: flex; justify-content: space-between; align-items: center; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
            <h4 style='margin: 0; color: white;'>Progress (This Group)</h4>
            <div>
                <span style='background-color: #28a745; color: white; padding: 5px 10px; border-radius: 15px; font-weight: bold;'>✅ {counted_items} Counted</span>
                <span style='background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 15px; font-weight: bold;'>❌ {total_items - counted_items} Pending</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # --- 5. THE COUNTING LIST (Numpad Optimized) ---
    with st.form("mobile_inventory_form"):
        if df_display.empty:
            st.info("No items found in this specific group. Please select another group.")
        else:
            for index, row in df_display.iterrows():
                item_name = row['item_name']
                
                is_counted = st.session_state['mobile_counts'].get(item_name) is not None
                status_emoji = "🟢" if is_counted else "🔴"
                
                col_name, col_input = st.columns([6, 4])
                with col_name:
                    st.markdown(f"**{status_emoji} {item_name}**")
                    st.caption(f"Unit: {row['unit']}")
                
                with col_input:
                    val = st.number_input(
                        "Qty", 
                        value=st.session_state['mobile_counts'].get(item_name, None),
                        min_value=0.0, 
                        step=None, 
                        key=f"input_{row['id']}",
                        label_visibility="collapsed"
                    )
                    
                    if val is not None:
                        st.session_state['mobile_counts'][item_name] = val
                
                st.divider()

        # --- 6. SAVE EVERYTHING TO DATABASE ---
        submit_btn = st.form_submit_button("🚀 SUBMIT ALL COUNTS TO CLOUD", use_container_width=True)
        
        if submit_btn:
            logs_to_insert = []
            
            # 1. Add standard items from session state
            for i_name, qty in st.session_state['mobile_counts'].items():
                if qty is not None and qty >= 0:
                    try:
                        item_info = df_client_items[df_client_items['item_name'] == i_name].iloc[0]
                        logs_to_insert.append({
                            "client_name": selected_client,
                            "date": str(count_date),
                            "location": selected_location,
                            "item_name": i_name,
                            "category": item_info['category'],
                            "group": item_info['group'],
                            "quantity": float(qty),
                            "unit": item_info['unit'],
                            "counted_by": user
                        })
                    except IndexError:
                        pass 
            
            # 2. Add custom/missing items from session state
            for custom in st.session_state['custom_items']:
                logs_to_insert.append({
                    "client_name": selected_client,
                    "date": str(count_date),
                    "location": selected_location,
                    "item_name": f"⚠️ {custom['item_name']}", # Marked so you know it was manually added
                    "category": custom['category'], # PERFECTLY MATCHES AUTO CALC NOW
                    "group": custom['group'],       # PERFECTLY MATCHES AUTO CALC NOW
                    "quantity": float(custom['quantity']),
                    "unit": custom['unit'],
                    "counted_by": user
                })
            
            if logs_to_insert:
                with st.spinner("Locking counts in the vault..."):
                    try:
                        supabase.table("inventory_logs").insert(logs_to_insert).execute()
                        st.success(f"✅ Successfully saved {len(logs_to_insert)} items!")
                        st.session_state['mobile_counts'] = {}
                        st.session_state['custom_items'] = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Database Error: {e}")
            else:
                st.warning("⚠️ You haven't counted anything yet!")