import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_main(conn, sheet_link, user, role):
    # 🚨 ENTERPRISE TIER SECURITY LOCK 
    user_role = role.lower()
    user_client = st.session_state.get('client_name', '').lower()
    
    is_super_admin = (user_role == "admin_all")
    is_normal_admin = (user_role == "admin")
    is_hq_manager = (user_role == "manager" and user_client == "all")

    if not (is_super_admin or is_normal_admin or is_hq_manager):
        st.error("🚫 Access Denied. This area is restricted to Head Office and Administrators.")
        return

    st.markdown("### ⚙️ Control Panel")
    supabase = get_supabase()

    # --- 🧠 INTELLIGENT ROUTING DATA ---
    def get_routing_df():
        records = []
        try:
            res1 = supabase.table("master_items").select("client_name, outlet, location").execute()
            if res1.data: records.extend(res1.data)
            res2 = supabase.table("users").select("client_name, outlet, location").execute()
            if res2.data: records.extend(res2.data)
        except: pass
        
        if records:
            df = pd.DataFrame(records)
            df['client_name'] = df['client_name'].astype(str).str.strip().str.title()
            df['outlet'] = df['outlet'].astype(str).str.strip().str.title()
            return df
        return pd.DataFrame(columns=['client_name', 'outlet', 'location'])

    df_routing = get_routing_df()

    # ==========================================
    # 📑 DYNAMIC TAB DEFINITION
    # ==========================================
    if is_super_admin:
        st.info("👑 Super Admin Mode: Full access to all database and user controls.")
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "👥 Manage Users", "🚚 Manage Suppliers", "📝 Edit Data"])
        t_sync, t_create, t_view, t_supp, t_edit = tabs
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: Access to sync and onboard users/suppliers.")
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "🚚 Manage Suppliers", "📝 Edit Data"])
        t_sync, t_create, t_supp, t_edit = tabs[0], tabs[1], tabs[2], tabs[3]
        t_view = None 
    else:
        st.info("🏢 HQ Manager Mode: Access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Sync"])
        t_sync = tabs[0]
        t_create = t_view = t_supp = t_edit = None

    # ==========================================
    # TAB: MASTER ITEMS SYNC
    # ==========================================
    with t_sync:

        sync_mode = st.radio("Select Sync Mode", 
                             ["🔄 Omega Sync (Auto Clean)", "📤 Smart Database Importer (Manual)"],
                             horizontal=True, key="sync_mode")

        # ── Helper: PROPER() equivalent ───────────────────────────────────────
        def proper(val):
            if pd.isna(val) or str(val).strip() == "": return ""
            return str(val).strip().title()

        def is_page_break_row(row):
            vals = [v for v in row if str(v) not in ["nan","NaT","None",""]]
            if not vals: return True
            if len(vals) <= 2 and any("page" in str(v).lower() for v in vals): return True
            return False

        # ══════════════════════════════════════════════════════════════════════
        # MODE 1: OMEGA SYNC
        # ══════════════════════════════════════════════════════════════════════
        if sync_mode == "🔄 Omega Sync (Auto Clean)":
            st.markdown("#### 🔄 Omega Sync — Auto Clean & Push")
            st.info("Upload the 2 Programming Summary files exported from Omega. Paperless will clean, apply PROPER(), and push to master_items automatically.")

            # ── Client setup ───────────────────────────────────────────────
            st.markdown("##### 1. Select or Create Client")
            
            existing_clients = sorted([c for c in df_routing["client_name"].unique() 
                                        if c and str(c).lower() not in ["nan","all",""]])
            
            client_mode = st.radio("Client", ["Select existing", "Create new"], 
                                    horizontal=True, key="omega_client_mode")
            
            col_c1, col_c2, col_c3 = st.columns(3)
            
            if client_mode == "Select existing":
                with col_c1:
                    sel_client = st.selectbox("🏢 Client", existing_clients, key="omega_client")
                with col_c2:
                    outlets = sorted([o for o in df_routing[df_routing["client_name"]==sel_client]["outlet"].unique()
                                     if o and str(o).lower() not in ["nan","all",""]])
                    sel_outlet = st.selectbox("🏠 Outlet", outlets if outlets else ["Main"], key="omega_outlet")
                with col_c3:
                    locs = set()
                    for lv in df_routing[(df_routing["client_name"]==sel_client)]["location"].dropna():
                        for l in str(lv).split(","):
                            if l.strip() and l.strip().lower() not in ["nan","all",""]:
                                locs.add(l.strip().title())
                    loc_list = sorted(list(locs)) if locs else ["Main Store"]
                    sel_location = st.selectbox("📍 Location", loc_list, key="omega_location")
                final_client   = sel_client
                final_outlet   = sel_outlet
                final_location = sel_location
            else:
                with col_c1: final_client   = st.text_input("🏢 New Client Name", key="omega_new_client").strip().title()
                with col_c2: final_outlet   = st.text_input("🏠 Outlet Name",     key="omega_new_outlet").strip().title()
                with col_c3: final_location = st.text_input("📍 Location Name",   key="omega_new_location").strip().title()

            if not final_client or not final_outlet or not final_location:
                st.warning("Please fill in Client, Outlet and Location before uploading files.")
                st.stop()

            st.markdown("##### 2. Upload Omega Files")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                inv_file  = st.file_uploader("📦 Programming Summary — Inventory", 
                                              type=["xlsx"], key="omega_inv")
            with col_f2:
                menu_file = st.file_uploader("🍽️ Programming Summary — Menu Items", 
                                              type=["xlsx"], key="omega_menu")

            # ── Parse Inventory file ───────────────────────────────────────
            def parse_inventory(f, client, outlet, location):
                raw = pd.read_excel(f, header=None)

                def is_sys(vals):
                    if not vals: return True
                    if len(vals) <= 3 and any("page" in str(v).lower() for v in vals): return True
                    if any(str(v).strip().lower() in ["item id","product code","buying u"] for v in vals): return True
                    if any(kw in str(v).lower() for v in vals
                           for kw in ["programming summary","copyright","omega software","www."]): return True
                    return False

                # Build clean sequence: ("text", value) or ("item", vals)
                # Skip first text row — it's always the client/outlet name from Omega
                clean = []
                first_text_skipped = False
                for _, row in raw.iterrows():
                    vals = [v for v in row.tolist() if str(v) not in ["nan","NaT","None",""]]
                    if is_sys(vals): continue
                    if len(vals) == 1:
                        val_str = str(vals[0]).strip()
                        try: float(val_str); continue
                        except ValueError: pass
                        # Skip the very first text row (client name)
                        if not first_text_skipped:
                            first_text_skipped = True
                            continue
                        clean.append(("text", val_str))
                    else:
                        try: int(float(str(vals[0])))
                        except (ValueError, TypeError): continue
                        clean.append(("item", vals))

                # Parse: two consecutive text rows = Category + Division (skip division)
                #        one text row alone = Sub-category
                records = []
                current_category     = ""
                current_sub_category = ""
                i = 0
                while i < len(clean):
                    rtype, rval = clean[i]
                    if rtype == "text":
                        if i+1 < len(clean) and clean[i+1][0] == "text":
                            # Category + Division pair
                            current_category     = proper(rval)
                            current_sub_category = ""
                            i += 2  # skip division row
                        else:
                            # Sub-category
                            current_sub_category = proper(rval)
                            i += 1
                    else:
                        vals = rval
                        try:
                            product_code = proper(vals[1]) if len(vals) > 1 else ""
                            item_name    = proper(vals[2]) if len(vals) > 2 else ""
                            count_unit   = proper(vals[5]) if len(vals) > 5 else (
                                           proper(vals[3]) if len(vals) > 3 else "")
                        except Exception:
                            i += 1; continue
                        if item_name:
                            records.append({
                                "client_name":   client,
                                "outlet":        outlet,
                                "location":      location,
                                "item_type":     "Inventory",
                                "category":      current_category,
                                "sub_category":  current_sub_category,
                                "product_code":  product_code,
                                "item_name":     item_name,
                                "count_unit":    count_unit,
                            })
                        i += 1
                return pd.DataFrame(records)

            # ── Parse Menu Items file ──────────────────────────────────────
            def parse_menu_items(f, client, outlet, location):
                raw = pd.read_excel(f, header=None)

                def is_sys_menu(vals):
                    if not vals: return True
                    if len(vals) <= 3 and any("page" in str(v).lower() for v in vals): return True
                    if any(str(v).strip().lower() in ["description","menu description",
                                                       "kitchen","item id","printout 1"] for v in vals): return True
                    if any(kw in str(v).lower() for v in vals
                           for kw in ["programming summary","copyright","omega software","www."]): return True
                    return False

                # Build clean sequence
                clean = []
                for _, row in raw.iterrows():
                    vals = [v for v in row.tolist() if str(v) not in ["nan","NaT","None",""]]
                    if is_sys_menu(vals): continue
                    if len(vals) == 1:
                        val_str = str(vals[0]).strip()
                        # Pure integer = ID row
                        try:
                            id_val = int(float(val_str))
                            clean.append(("id", id_val))
                            continue
                        except ValueError:
                            pass
                        clean.append(("text", val_str))
                    else:
                        name = str(vals[0]).strip()
                        if name and name.upper() != "DONE" and name.lower() != "item id":
                            clean.append(("item", vals))

                # Parse: two consecutive text rows = Category + Division (skip division)
                #        one text row alone = Sub-category
                #        item row followed by id row → product_code = id
                records = []
                current_category     = ""
                current_sub_category = ""
                i = 0
                while i < len(clean):
                    rtype, rval = clean[i]

                    if rtype == "text":
                        if i+1 < len(clean) and clean[i+1][0] == "text":
                            current_category     = proper(rval)
                            current_sub_category = ""
                            i += 2
                        else:
                            current_sub_category = proper(rval)
                            i += 1

                    elif rtype == "item":
                        item_name    = proper(rval[0])
                        product_code = item_name  # fallback
                        if i+1 < len(clean) and clean[i+1][0] == "id":
                            product_code = str(clean[i+1][1])
                            i += 1  # consume ID row

                        if item_name:
                            records.append({
                                "client_name":   client,
                                "outlet":        outlet,
                                "location":      location,
                                "item_type":     "Menu Items",
                                "category":      current_category,
                                "sub_category":  current_sub_category,
                                "product_code":  product_code,
                                "item_name":     item_name,
                                "count_unit":    "Unit",
                            })
                        i += 1

                    else:
                        i += 1  # orphan ID

                return pd.DataFrame(records)

            # ── Preview & Push ─────────────────────────────────────────────
            if inv_file or menu_file:
                st.markdown("##### 3. Preview Cleaned Data")
                
                df_inv  = pd.DataFrame()
                df_menu = pd.DataFrame()
                
                if inv_file:
                    try:
                        df_inv = parse_inventory(inv_file, final_client, final_outlet, final_location)
                        st.markdown(f"**Inventory Items:** {len(df_inv)} rows cleaned")
                        st.dataframe(df_inv.head(10), use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.error(f"❌ Inventory parse error: {e}")
                
                if menu_file:
                    try:
                        df_menu = parse_menu_items(menu_file, final_client, final_outlet, final_location)
                        st.markdown(f"**Menu Items:** {len(df_menu)} rows cleaned")
                        st.dataframe(df_menu.head(10), use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.error(f"❌ Menu Items parse error: {e}")
                
                combined = pd.concat([df_inv, df_menu], ignore_index=True)
                
                if len(combined) > 0:
                    st.markdown(f"##### 4. Push to Supabase")
                    st.markdown(f"**Total records to upsert: {len(combined)}** "
                                f"({len(df_inv)} inventory + {len(df_menu)} menu items)")
                    
                    if st.button("🚀 Push to Supabase", type="primary", 
                                  use_container_width=True, key="omega_push"):
                        with st.spinner("Pushing to Supabase..."):
                            try:
                                combined = combined.fillna("")
                                records  = combined.to_dict(orient="records")
                                pushed   = 0
                                for i in range(0, len(records), 500):
                                    supabase.table("master_items").upsert(
                                        records[i:i+500],
                                        on_conflict="client_name,outlet,location,item_type,product_code"
                                    ).execute()
                                    pushed += len(records[i:i+500])
                                st.success(f"✅ Done! {pushed} items pushed to Supabase for {final_client}.")
                                st.balloons()
                            except Exception as e:
                                st.error(f"❌ Push failed: {e}")

        # ══════════════════════════════════════════════════════════════════════
        # MODE 2: SMART DATABASE IMPORTER (existing, unchanged)
        # ══════════════════════════════════════════════════════════════════════
        else:
            st.markdown("#### 📤 Smart Database Importer")
            uploaded_file = st.file_uploader("Upload Master Items List", type=["csv", "xlsx"])
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                    df.columns = [str(c).strip().lower() for c in df.columns]
                    st.dataframe(df.head(5), use_container_width=True)
                    required_cols = ['client_name', 'outlet', 'location', 'item_type', 'product_code', 'item_name']
                    if all(c in df.columns for c in required_cols):
                        if st.button("🚀 Run Smart Sync", type="primary", use_container_width=True):
                            with st.spinner("Syncing..."):
                                df = df.fillna('')
                                records = df.to_dict(orient='records')
                                for i in range(0, len(records), 500):
                                    supabase.table("master_items").upsert(records[i:i + 500], on_conflict="client_name,outlet,location,item_type,product_code").execute()
                                st.success(f"✅ Synced {len(records)} items!")
                    else:
                        st.error("❌ Missing required columns.")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

    # ==========================================
    # TAB: CREATE USER
    # ==========================================
    if t_create:
        with t_create:
            st.subheader("Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("👤 Username", key="c_usr")
                new_password = st.text_input("🔑 Password", key="c_pwd")
                new_fullname = st.text_input("📝 Full Name", key="c_name")
                role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                new_role = st.selectbox("🛡️ Role", role_options, key="c_role")
            with col2:
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger"]
                new_modules = st.multiselect("📱 App Access", available_modules, default=["waste"], key="c_mod")

            # 🚀 FILTER FIX: Remove "All" from the database pulls so it doesn't duplicate!
            c_list = ["All"] + sorted([c for c in df_routing['client_name'].unique() if c and str(c).lower() not in ['nan', 'all']])
            col3, col4, col5 = st.columns(3)
            with col3: new_client = st.selectbox("🏢 Select Client", c_list, key="c_client")
            
            f_outlets = df_routing['outlet'].unique() if new_client == "All" else df_routing[df_routing['client_name'] == new_client]['outlet'].unique()
            # 🚀 FILTER FIX
            o_list = ["All"] + sorted([o for o in f_outlets if o and str(o).lower() not in ['nan', 'all']])
            with col4: new_outlet = st.selectbox("🏠 Select Outlet", o_list, key="c_outlet")
            
            loc_df = df_routing.copy()
            if new_client != "All": loc_df = loc_df[loc_df['client_name'] == new_client]
            if new_outlet != "All": loc_df = loc_df[loc_df['outlet'] == new_outlet]
            loc_set = set()
            for loc_val in loc_df['location'].dropna():
                for l in str(loc_val).split(','):
                    if l.strip() and str(l).lower() not in ['nan', 'all']: loc_set.add(l.strip().title())
            # 🚀 FILTER FIX
            l_list = ["All"] + sorted(list(loc_set))
            with col5: new_locations = st.multiselect("📍 Select Location(s)", l_list, default=["All"], key="c_loc")

            if st.button("🚀 CREATE USER", type="primary", use_container_width=True):
                new_user_data = {
                    "username": new_username.strip(), "password": new_password.strip(), "full_name": new_fullname.strip(),
                    "role": new_role, "client_name": new_client, "outlet": new_outlet,
                    "location": ", ".join(new_locations), "module": ", ".join(new_modules)
                }
                supabase.table("users").insert([new_user_data]).execute()
                st.success("✅ User created!")

    # ==========================================
    # TAB: MANAGE USERS (Super Admin Only)
    # ==========================================
    if t_view:
        with t_view:
            try:
                res = supabase.table("users").select("*").execute()
                if res.data:
                    df_u = pd.DataFrame(res.data)
                    u_sel = st.selectbox("👤 Select User to Edit", sorted(df_u['username'].tolist()), key="e_user_sel")
                    u_data = df_u[df_u['username'] == u_sel].iloc[0]
                    
                    st.divider()
                    st.subheader(f"⚙️ Editing User: {u_sel}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        e_pass = st.text_input("🔑 Password", value=u_data.get('password', ''))
                        e_fullname = st.text_input("📝 Full Name", value=u_data.get('full_name', ''))
                        
                        role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                        e_role_index = role_options.index(u_data['role']) if u_data['role'] in role_options else 0
                        e_role = st.selectbox("🛡️ Role", role_options, index=e_role_index)
                        
                    with col2:
                        # 👇 THIS IS WHERE IT WAS MISSING! 👇
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger"]
                        current_mods = [m.strip() for m in str(u_data.get('module', '')).split(',')] if str(u_data.get('module', '')) else ["waste"]
                        valid_mods = [m for m in current_mods if m in available_modules]
                        e_modules = st.multiselect("📱 App Access", available_modules, default=valid_mods)

                    # 🚀 FILTER FIX: Remove "All" from the database pulls so it doesn't duplicate!
                    c_list = ["All"] + sorted([c for c in df_routing['client_name'].unique() if c and str(c).lower() not in ['nan', 'all']])
                    col3, col4, col5 = st.columns(3)
                    with col3: 
                        c_index = c_list.index(u_data['client_name']) if u_data['client_name'] in c_list else 0
                        e_client = st.selectbox("🏢 Select Client", c_list, index=c_index, key="e_client_box")
                    
                    f_outlets = df_routing['outlet'].unique() if e_client == "All" else df_routing[df_routing['client_name'] == e_client]['outlet'].unique()
                    # 🚀 FILTER FIX
                    o_list = ["All"] + sorted([o for o in f_outlets if o and str(o).lower() not in ['nan', 'all']])
                    with col4: 
                        o_index = o_list.index(u_data['outlet']) if u_data['outlet'] in o_list else 0
                        e_outlet = st.selectbox("🏠 Select Outlet", o_list, index=o_index, key="e_outlet_box")
                    
                    loc_df = df_routing.copy()
                    if e_client != "All": loc_df = loc_df[loc_df['client_name'] == e_client]
                    if e_outlet != "All": loc_df = loc_df[loc_df['outlet'] == e_outlet]
                    loc_set = set()
                    for loc_val in loc_df['location'].dropna():
                        for l in str(loc_val).split(','):
                            if l.strip() and str(l).lower() not in ['nan', 'all']: loc_set.add(l.strip().title())
                    # 🚀 FILTER FIX
                    l_list = ["All"] + sorted(list(loc_set))
                    
                    current_locs = [l.strip() for l in str(u_data.get('location', '')).split(',')] if str(u_data.get('location', '')) else ["All"]
                    valid_locs = [l for l in current_locs if l in l_list]
                    if not valid_locs: valid_locs = ["All"]
                    
                    with col5: 
                        e_locations = st.multiselect("📍 Select Location(s)", l_list, default=valid_locs, key="e_loc_box")

                    st.write("") # Quick spacer
                    if st.button("💾 Save User Changes", type="primary", use_container_width=True):
                        update_payload = {
                            "password": e_pass, 
                            "full_name": e_fullname,
                            "role": e_role,
                            "module": ", ".join(e_modules),
                            "client_name": e_client,
                            "outlet": e_outlet,
                            "location": ", ".join(e_locations)
                        }
                        supabase.table("users").update(update_payload).eq("username", u_sel).execute()
                        st.success(f"✅ User '{u_sel}' updated successfully!")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Error loading user manager: {e}")

    # ==========================================
    # TAB: MANAGE SUPPLIERS
    # ==========================================
    if t_supp:
        with t_supp:
            st.markdown("#### 🚚 Supplier Management")
            try:
                s_res = supabase.table("suppliers").select("*").execute()
                existing_s = pd.DataFrame(s_res.data) if s_res.data else pd.DataFrame(columns=["supplier_name"])
                
                c1, c2 = st.columns(2)
                with c1:
                    with st.form("add_supp", clear_on_submit=True):
                        n_s = st.text_input("New Supplier Name")
                        if st.form_submit_button("➕ Add Supplier"):
                            clean_n = n_s.strip().lower()
                            existing_list = [x.lower() for x in existing_s['supplier_name'].tolist()]
                            if clean_n in existing_list:
                                st.warning("⚠️ Already exists!")
                            else:
                                supabase.table("suppliers").insert({"supplier_name": n_s.title()}).execute()
                                st.success("Added!")
                                st.rerun()
                with c2:
                    st.write("**Current List:**")
                    st.dataframe(existing_s[['supplier_name']].sort_values('supplier_name'), hide_index=True, use_container_width=True)
                    s_del = st.selectbox("Delete Supplier", existing_s['supplier_name'].tolist(), index=None)
                    if st.button("🗑️ Delete"):
                        supabase.table("suppliers").delete().eq("supplier_name", s_del).execute()
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # ==========================================
    # TAB: LIVE DATA EDITOR (The God Mode)
    # ==========================================
    if t_edit:
        with t_edit:
            st.markdown("#### 📝 Live Database Editor")
            st.info("💡 Double-click any cell to edit it. When you are finished, click the Save button at the bottom.")
            
            # 👇 I added "ledger_logs" here for you too!
            table_to_edit = st.selectbox("🗄️ Select Table to Edit:", ["waste_logs", "invoices_log", "ledger_logs"])
            
            try:
                # Fetch the last 150 records (we limit it so the app doesn't freeze on huge datasets)
                res = supabase.table(table_to_edit).select("*").order("id", desc=True).limit(150).execute()
                
                if res.data:
                    df_edit = pd.DataFrame(res.data)
                    
                    # 1. DISPLAY THE SPREADSHEET
                    edited_df = st.data_editor(
                        df_edit,
                        use_container_width=True,
                        disabled=["id", "created_at"], # Protect the ID so they don't break the database
                        hide_index=True,
                        key=f"editor_{table_to_edit}"
                    )
                    
                    # 2. THE SAVE LOGIC
                    st.write("")
                    if st.button(f"💾 Save Changes to {table_to_edit}", type="primary", use_container_width=True):
                        with st.spinner("Scanning for changes and updating cloud..."):
                            updates_made = 0
                            
                            # We fill empty cells to make comparing them easier
                            safe_edited_df = edited_df.fillna('')
                            safe_orig_df = df_edit.fillna('')
                            
                            for index, new_row in safe_edited_df.iterrows():
                                old_row = safe_orig_df.loc[index]
                                
                                # If the row was changed by the user:
                                if new_row.to_dict() != old_row.to_dict():
                                    row_id = new_row['id']
                                    
                                    # Prepare the update package (we strip out 'id' and 'created_at' to be safe)
                                    update_payload = edited_df.loc[index].drop(['id', 'created_at']).to_dict()
                                    
                                    # Send the update to Supabase
                                    supabase.table(table_to_edit).update(update_payload).eq("id", row_id).execute()
                                    updates_made += 1
                            
                            if updates_made > 0:
                                st.success(f"✅ Successfully updated {updates_made} record(s)!")
                                st.rerun()
                            else:
                                st.info("No changes were detected.")
                else:
                    st.warning("No records found in this table.")
            except Exception as e:
                st.error(f"❌ Error loading data: {e}")