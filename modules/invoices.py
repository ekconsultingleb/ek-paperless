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
    outlet = st.session_state.get('outlet', 'Unknown')
    location = st.session_state.get('location', 'Unknown')
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
            st.info("💡 **Data Entry Mode:** Select a pending invoice below. View the image, type your notes, and mark it as Posted.")
            
            try:
                # 1. Fetch only invoices that need attention!
                query = supabase.table("invoices_log").select("*").in_("status", ["Pending", "On Hold"])
                
                # Apply security routing so a franchise manager only sees their own restaurants
                if client_name != "All":
                    query = query.eq("client_name", client_name)
                if outlet != "All":
                    query = query.eq("outlet", outlet)
                    
                res = query.execute()
                
                if not res.data:
                    st.success("🎉 All caught up! There are no Pending or On Hold invoices to process.")
                else:
                    df = pd.DataFrame(res.data)
                    
                    # Sort so oldest is at the top (First in, First out)
                    df = df.sort_values(by="created_at", ascending=True)
                    
                    # Create a nice display name for the dropdown
                    df['display_name'] = df['created_at'].str[:10] + " | " + df['supplier'] + " | " + df['outlet'] + " (" + df['status'] + ")"
                    
                    selected_disp = st.selectbox("📥 Select an Invoice to Process", df['display_name'].tolist())
                    
                    if selected_disp:
                        # Find the exact row the user clicked on
                        selected_row = df[df['display_name'] == selected_disp].iloc[0]
                        invoice_id = selected_row['id']
                        
                        st.divider()
                        
                        # -- The Master/Detail Layout --
                        col1, col2 = st.columns([1.2, 1]) # Left column is slightly wider for the picture
                        
                        with col1:
                            st.markdown("#### 🖼️ Invoice Document")
                            st.image(selected_row['image_url'], use_container_width=True)
                            # Give Bassel a link to open it huge in a new tab if he needs to zoom in!
                            st.markdown(f"[🔍 Click here to open full size image in a new tab]({selected_row['image_url']})")
                            
                        with col2:
                            st.markdown("#### 📝 Data Entry Actions")
                            st.write(f"**🏢 Branch:** {selected_row['client_name']} - {selected_row['outlet']} ({selected_row['location']})")
                            st.write(f"**🚚 Supplier:** {selected_row['supplier']}")
                            st.write(f"**👤 Uploaded By:** {selected_row['uploaded_by']}")
                            st.write(f"**📅 Date:** {selected_row['created_at'][:16]}")
                            
                            # The Form where Bassel does his work
                            with st.form(f"process_form_{invoice_id}"):
                                current_status = selected_row.get('status', 'Pending')
                                status_options = ["Pending", "On Hold", "Posted"]
                                
                                new_status = st.radio(
                                    "Status", 
                                    status_options, 
                                    index=status_options.index(current_status) if current_status in status_options else 0,
                                    horizontal=True
                                )
                                
                                new_notes = st.text_area(
                                    "Data Entry Notes (e.g., 'Messaged Chef about missing page')", 
                                    value=selected_row.get('data_entry_notes', '') or ""
                                )
                                
                                submit_process = st.form_submit_button("💾 Save & Update", type="primary", use_container_width=True)
                                
                                if submit_process:
                                    if user_role == "viewer":
                                        st.error("🚫 Access Denied: Viewers cannot modify invoice records.")
                                    else:
                                        update_data = {
                                            "status": new_status,
                                            "data_entry_notes": new_notes,
                                            # If he marks it posted, record his name permanently
                                            "posted_by": user if new_status == "Posted" else selected_row.get('posted_by', None)
                                        }
                                        supabase.table("invoices_log").update(update_data).eq("id", invoice_id).execute()
                                        st.success(f"✅ Invoice successfully updated to: {new_status}")
                                        st.rerun()
                                        
            except Exception as e:
                st.error(f"❌ Error loading dashboard: {e}")


    # ==========================================
    # VIEW 2: SNAP INVOICE (Everyone sees this)
    # ==========================================
    with tab_upload:
        st.info("💡 **Mobile Users:** Tap 'Browse files' to open your camera and take a photo of the receipt.")
        
        supplier_name = st.text_input("🏢 Supplier Name", placeholder="e.g. Tanmia, Bocti, Wesley's Wholesale")
        
        # The Magic Mobile Picker
        uploaded_file = st.file_uploader("Take a Photo or Upload PDF", type=['jpg', 'jpeg', 'png', 'pdf'])
        
        if uploaded_file is not None:
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption="Invoice Preview", use_container_width=True)
            else:
                st.success(f"📄 PDF Selected: {uploaded_file.name}")
        
        st.write("") 
        submit_btn = st.button("🚀 Submit Invoice to Accounting", type="primary", use_container_width=True)

        if submit_btn:
            if not supplier_name:
                st.error("❌ Please enter the Supplier Name.")
            elif not uploaded_file:
                st.error("❌ Please take a photo of the invoice first.")
            else:
                with st.spinner("Uploading securely to the cloud... please wait..."):
                    try:
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        unique_filename = f"{client_name.replace(' ', '')}_{uuid.uuid4().hex[:8]}.{file_ext}"
                        
                        file_bytes = uploaded_file.getvalue()
                        supabase.storage.from_("invoices").upload(
                            path=unique_filename,
                            file=file_bytes,
                            file_options={"content-type": uploaded_file.type}
                        )
                        
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)
                        
                        db_record = {
                            "client_name": client_name,
                            "outlet": outlet,
                            "location": location,
                            "uploaded_by": user,
                            "supplier": supplier_name.strip().title(),
                            "image_url": image_url,
                            "status": "Pending",
                            "data_entry_notes": ""
                        }
                        
                        supabase.table("invoices_log").insert([db_record]).execute()
                        
                        # 1. Show the success message
                        st.success("✅ Invoice successfully uploaded and sent to Accounting!")
                        
                        # 2. Add a sleek mobile popup (Toast) just to be safe
                        st.toast("Invoice sent to Accounting!", icon="🚀")
                        
                        # 3. Automatically smooth-scroll to the bottom of the page
                        st.markdown(
                            "<script>window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });</script>",
                            unsafe_allow_html=True
                        )
                        
                    except Exception as e: