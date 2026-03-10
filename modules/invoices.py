import streamlit as st
import pandas as pd
import uuid
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_invoices(conn, sheet_link, user, role):
    supabase = get_supabase()
    
    # Grab the user's routing info from the session
    client_name = st.session_state.get('client_name', 'Unknown')
    outlet = st.session_state.get('assigned_outlet', 'Unknown')
    location = st.session_state.get('assigned_location', 'Unknown')
    user_role = str(role).lower()

    # 🚦 TRAFFIC COP: Who sees what?
    can_process_invoices = user_role in ["manager", "admin", "admin_all", "viewer"]

    # --- SET UP THE SPLIT SCREEN ---
    if can_process_invoices:
        st.markdown("### 🏢 Accounts Payable Dashboard")
        tab_process, tab_upload = st.tabs(["📋 Process Invoices", "📸 Upload Invoice"])
    else:
        st.markdown("### 📸 Snap & Upload Invoice")
        tab_upload = st.container() # Staff only gets the upload screen, no tabs
        tab_process = None

    # ==========================================
    # VIEW 1: DATA ENTRY DASHBOARD (Bassel's View)
    # ==========================================
    if tab_process:
        with tab_process:
            # -----------------------------------------------------------
            # THE HEALTHY LINK: If an invoice is selected, show the form!
            # -----------------------------------------------------------
            if 'processing_inv_id' in st.session_state:
                target_id = st.session_state['processing_inv_id']
                target_client = st.session_state['processing_client']
                
                # Back button to return to the list
                if st.button("⬅️ Back to Pending List"):
                    del st.session_state['processing_inv_id']
                    del st.session_state['processing_client']
                    st.rerun()
                
                st.subheader(f"📝 Processing Invoice #{target_id} | {target_client}")
                st.divider()
                
                # Fetch only this specific invoice securely
                try:
                    res = supabase.table("invoices_log").select("*").eq("id", target_id).eq("client_name", target_client).execute()
                    
                    if res.data:
                        selected_row = res.data[0]
                        
                        col1, col2 = st.columns([1.2, 1])
                        with col1:
                            st.markdown("#### 🖼️ Invoice Document")
                            st.image(selected_row['image_url'], use_container_width=True, output_format="JPEG")
                            st.markdown(f"[🔍 Click here to open full size image in a new tab]({selected_row['image_url']})")
                            
                        with col2:
                            st.markdown("#### 📝 Data Entry Actions")
                            st.write(f"**🏢 Branch:** {selected_row['client_name']} - {selected_row['outlet']}")
                            st.write(f"**🚚 Supplier:** {selected_row['supplier']}")
                            st.write(f"**📅 Date Uploaded:** {str(selected_row['created_at'])[:10]}")
                            st.write(f"**👤 Uploaded By:** {selected_row['uploaded_by']}")
                            
                            with st.form(f"process_form_{target_id}"):
                                # New Financial Fields
                                amount = st.number_input("💵 Total Invoice Amount", value=float(selected_row.get('amount') or 0.0), min_value=0.0, step=0.01)
                                tax = st.number_input("🏛️ Tax Amount (VAT)", value=float(selected_row.get('tax') or 0.0), min_value=0.0, step=0.01)
                                
                                current_status = selected_row.get('status', 'Pending')
                                status_options = ["Pending", "On Hold", "Posted"]
                                new_status = st.radio("Status", status_options, index=status_options.index(current_status) if current_status in status_options else 0, horizontal=True)
                                
                                new_notes = st.text_area("Data Entry Notes", value=selected_row.get('data_entry_notes', '') or "")
                                
                                if st.form_submit_button("💾 Save & Update", type="primary", use_container_width=True):
                                    if user_role == "viewer":
                                        st.error("🚫 Access Denied: Viewers cannot modify records.")
                                    else:
                                        # SECURE UPDATE LINKED DIRECTLY TO ID & CLIENT
                                        update_data = {
                                            "amount": amount,
                                            "tax": tax,
                                            "status": new_status, 
                                            "data_entry_notes": new_notes, 
                                            "posted_by": user if new_status == "Posted" else selected_row.get('posted_by', None)
                                        }
                                        supabase.table("invoices_log").update(update_data).eq("id", target_id).eq("client_name", target_client).execute()
                                        
                                        st.success(f"✅ Invoice #{target_id} updated successfully!")
                                        # Clear state and return to grid
                                        del st.session_state['processing_inv_id']
                                        del st.session_state['processing_client']
                                        st.rerun()
                    else:
                        st.error("Could not find this invoice in the database.")
                except Exception as e:
                    st.error(f"❌ Error loading invoice: {e}")

            # -----------------------------------------------------------
            # THE GRID VIEW: Show the list of pending invoices
            # -----------------------------------------------------------
            else:
                st.info("💡 **Data Entry Mode:** Click 'Process' next to an invoice below to enter the financials and mark it as Posted.")
                
                try:
                    # Fetch invoices that need attention
                    query = supabase.table("invoices_log").select("*").in_("status", ["Pending", "On Hold"])
                    
                    if client_name != "All":
                        query = query.eq("client_name", client_name)
                    if outlet != "All":
                        query = query.eq("outlet", outlet)
                        
                    res = query.execute()
                    
                    if not res.data:
                        st.success("🎉 All caught up! There are no Pending or On Hold invoices to process.")
                    else:
                        df = pd.DataFrame(res.data)
                        df = df.sort_values(by="created_at", ascending=True)
                        
                        # --- 🧠 SMART CLIENT FILTER FOR BASSEL ---
                        if client_name == "All":
                            active_clients = ["All Clients"] + sorted(df['client_name'].unique().tolist())
                            st.markdown("#### 🎯 Filter Workspace")
                            chosen_client = st.selectbox("Select a Client to focus on:", active_clients)
                            if chosen_client != "All Clients":
                                df = df[df['client_name'] == chosen_client]
                        
                        if df.empty:
                            st.info("✅ No pending invoices for this specific client.")
                        else:
                            st.markdown("#### 📥 Pending Invoices")
                            
                            # Build the interactive grid
                            for index, row in df.iterrows():
                                inv_id = row['id']
                                c_name = row['client_name']
                                
                                with st.container(border=True):
                                    col_date, col_sup, col_loc, col_stat, col_btn = st.columns([1.5, 2, 2, 1, 1], vertical_alignment="center")
                                    
                                    col_date.write(f"📅 {str(row['created_at'])[:10]}")
                                    col_sup.write(f"🧾 **{row['supplier']}**")
                                    col_loc.write(f"🏢 {c_name} ({row['outlet']})")
                                    
                                    # Status badges
                                    if row['status'] == 'On Hold':
                                        col_stat.error("⏸️ On Hold")
                                    else:
                                        col_stat.warning("⏳ Pending")
                                        
                                    with col_btn:
                                        # 🔒 THE TRIGGER: Push the exact ID to memory and refresh
                                        if st.button("⚙️ Process", key=f"process_btn_{inv_id}", use_container_width=True):
                                            st.session_state['processing_inv_id'] = inv_id
                                            st.session_state['processing_client'] = c_name
                                            st.rerun()
                                            
                except Exception as e:
                    st.error(f"❌ Error loading dashboard: {e}")

    # ==========================================
    # VIEW 2: SNAP INVOICE (Everyone sees this)
    # ==========================================
    with tab_upload:
        st.info("💡 **Mobile Users:** Tap 'Browse files' to open your camera.")
        
        # --- 🧠 BULLETPROOF MOBILE SUPPLIER SEARCH ---
        try:
            sup_res = supabase.table("suppliers").select("supplier_name").execute()
            supplier_list = sorted([row['supplier_name'] for row in sup_res.data]) if sup_res.data else []
        except Exception:
            supplier_list = []
            
        search_term = st.text_input("🔍 Search Supplier", placeholder="Type here to filter the list below...")
        
        if search_term:
            filtered_suppliers = [s for s in supplier_list if search_term.lower() in s.lower()]
            if "➕ Other (Type manually)" not in filtered_suppliers:
                filtered_suppliers.append("➕ Other (Type manually)")
        else:
            filtered_suppliers = supplier_list + ["➕ Other (Type manually)"]

        selected_supplier = st.selectbox("🏢 Choose from Results", filtered_suppliers)
        
        if selected_supplier == "➕ Other (Type manually)":
            final_supplier_name = st.text_input("📝 Type the new supplier name:")
        else:
            final_supplier_name = selected_supplier
        
        uploaded_file = st.file_uploader("Take a Photo or Upload PDF", type=['jpg', 'jpeg', 'png', 'pdf'])
        
        if uploaded_file:
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption="Invoice Preview", use_container_width=True)
            else:
                st.success(f"📄 PDF Selected: {uploaded_file.name}")
        
        if st.button("🚀 Submit Invoice to Accounting", type="primary", use_container_width=True):
            if not final_supplier_name:
                st.error("❌ Please select a Supplier.")
            elif not uploaded_file:
                st.error("❌ Please upload or take a photo.")
            else:
                with st.spinner("Uploading..."):
                    try:
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        unique_filename = f"{client_name.replace(' ', '')}_{uuid.uuid4().hex[:8]}.{file_ext}"
                        
                        supabase.storage.from_("invoices").upload(path=unique_filename, file=uploaded_file.getvalue(), file_options={"content-type": uploaded_file.type})
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)
                        
                        db_record = {
                            "client_name": client_name, "outlet": outlet, "location": location,
                            "uploaded_by": user, "supplier": final_supplier_name.strip().title(),
                            "image_url": image_url, "status": "Pending", "data_entry_notes": ""
                            # Note: amount and tax will default to NULL/0 in Supabase until processed
                        }
                        supabase.table("invoices_log").insert([db_record]).execute()
                        
                        st.success("✅ Invoice successfully uploaded!")
                        st.toast("Invoice sent!", icon="🚀")
                        st.markdown("<script>window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });</script>", unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"❌ Error: {e}")