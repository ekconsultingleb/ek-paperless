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
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices"]
                        current_mods = [m.strip() for m in str(u_data.get('module', '')).split(',')] if str(u_data.get('module', '')) else ["waste"]
                        valid_mods = [m for m in current_mods if m in available_modules]
                        e_modules = st.multiselect("📱 App Access", available_modules, default=valid_mods)

                    c_list = ["All"] + sorted([c for c in df_routing['client_name'].unique() if c and str(c).lower() != 'nan'])
                    col3, col4, col5 = st.columns(3)
                    with col3: 
                        c_index = c_list.index(u_data['client_name']) if u_data['client_name'] in c_list else 0
                        e_client = st.selectbox("🏢 Select Client", c_list, index=c_index, key="e_client_box")
                    
                    f_outlets = df_routing['outlet'].unique() if e_client == "All" else df_routing[df_routing['client_name'] == e_client]['outlet'].unique()
                    o_list = ["All"] + sorted([o for o in f_outlets if o and str(o).lower() != 'nan'])
                    with col4: 
                        o_index = o_list.index(u_data['outlet']) if u_data['outlet'] in o_list else 0
                        e_outlet = st.selectbox("🏠 Select Outlet", o_list, index=o_index, key="e_outlet_box")
                    
                    loc_df = df_routing.copy()
                    if e_client != "All": loc_df = loc_df[loc_df['client_name'] == e_client]
                    if e_outlet != "All": loc_df = loc_df[loc_df['outlet'] == e_outlet]
                    loc_set = set(["All"])
                    for loc_val in loc_df['location'].dropna():
                        for l in str(loc_val).split(','):
                            if l.strip() and str(l).lower() != 'nan': loc_set.add(l.strip())
                    l_list = sorted(list(loc_set))
                    
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