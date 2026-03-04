import streamlit as st
import uuid
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_invoices(conn, sheet_link, user, role):
    st.markdown("### 📸 Snap & Upload Invoice")
    
    # Grab the user's routing info from the session
    client_name = st.session_state.get('client_name', 'Unknown')
    outlet = st.session_state.get('outlet', 'Unknown')
    location = st.session_state.get('location', 'Unknown')

    supabase = get_supabase()

    # The clean UI for the Chef
    with st.container():
        st.info("💡 **Mobile Users:** Tap 'Browse files' to open your camera and take a photo of the receipt.")
        
        supplier_name = st.text_input("🏢 Supplier Name", placeholder="e.g. Interal, Bocti, Tannourine")
        
        # The Magic Mobile Picker (Allows images and PDFs)
        uploaded_file = st.file_uploader("Take a Photo or Upload PDF", type=['jpg', 'jpeg', 'png', 'pdf'])
        
        # Show a preview so the Chef knows it worked
        if uploaded_file is not None:
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption="Invoice Preview", use_container_width=True)
            else:
                st.success(f"📄 PDF Selected: {uploaded_file.name}")
        
        st.write("") # Spacer
        submit_btn = st.button("🚀 Submit Invoice to Accounting", type="primary", use_container_width=True)

        # The Cloud Upload Logic
        if submit_btn:
            if not supplier_name:
                st.error("❌ Please enter the Supplier Name.")
            elif not uploaded_file:
                st.error("❌ Please take a photo of the invoice first.")
            else:
                with st.spinner("Uploading securely to the cloud... please wait..."):
                    try:
                        # 1. Generate a secure, unique file name (e.g., LaSiesta_8f7d9a2b.jpg)
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        unique_filename = f"{client_name.replace(' ', '')}_{uuid.uuid4().hex[:8]}.{file_ext}"
                        
                        # 2. Upload the actual picture to your 'invoices' Bucket
                        file_bytes = uploaded_file.getvalue()
                        supabase.storage.from_("invoices").upload(
                            path=unique_filename,
                            file=file_bytes,
                            file_options={"content-type": uploaded_file.type}
                        )
                        
                        # 3. Ask the Bucket for the Public URL Link
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)
                        
                        # 4. Save the details to your new SQL table!
                        db_record = {
                            "client_name": client_name,
                            "outlet": outlet,
                            "location": location,
                            "uploaded_by": user,
                            "supplier": supplier_name.strip().title(),
                            "image_url": image_url,
                            "status": "Pending"
                            # data_entry_notes and posted_by are left blank for Bassel!
                        }
                        
                        supabase.table("invoices_log").insert([db_record]).execute()
                        
                        st.success("✅ Invoice successfully uploaded and sent to Accounting!")
                        st.balloons()
                        
                    except Exception as e:
                        st.error(f"❌ Error uploading: {e}")
                        st.caption("Did you make sure the bucket is named exactly 'invoices' and is set to Public?")