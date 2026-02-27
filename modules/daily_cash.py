import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_daily_cash(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🏦 Daily Cash Report")
    supabase = get_supabase()
    
    try:
        # ==========================================
        # 1. VIEWER MODE (WITH DATE RANGE)
        # ==========================================
        if role.lower() == "viewer":
            st.info("👁️ Viewer Mode: Showing Daily Cash Logs")
            
            # Date Range Selector
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=7)
            
            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                
                # Build the query
                query = supabase.table("daily_cash").select("*").gte("date", str(start_date)).lte("date", str(end_date))
                
                if str(assigned_client).lower() != 'all':
                    query = query.ilike("client_name", f"%{str(assigned_client).strip()}%")
                    
                archive_res = query.order("date", desc=True).limit(1000).execute()
                df_archive = pd.DataFrame(archive_res.data)

                if not df_archive.empty:
                    # Format financial columns to look nice
                    currency_cols = ['main_reading', 'cash', 'visa', 'expenses', 'on_account', 'revenue', 'over_short']
                    for col in currency_cols:
                        if col in df_archive.columns:
                            df_archive[col] = df_archive[col].apply(lambda x: f"{float(x):,.2f}" if pd.notnull(x) else "0.00")
                            
                    st.dataframe(df_archive, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No cash reports found between {start_date} and {end_date}.")
            else:
                st.info("Please select both a Start Date and an End Date.")
            return

        # ==========================================
        # 2. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        nav_res = supabase.table("master_items").select("client_name, outlet").execute()
        df_nav = pd.DataFrame(nav_res.data)
        
        if not df_nav.empty:
            df_nav['client_name'] = df_nav['client_name'].astype(str).str.strip().str.title()
            df_nav['outlet'] = df_nav['outlet'].astype(str).str.strip().str.title()
            
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        st.sidebar.markdown("### 📍 Location Details")

        if clean_client.lower() != 'all':
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = sorted(df_nav['client_name'].unique()) if not df_nav.empty else ["All"]
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list)

        if not df_nav.empty:
            outlets_for_client = sorted(df_nav[df_nav['client_name'] == final_client]['outlet'].unique())
        else:
            outlets_for_client = []

        if clean_outlet.lower() != 'all':
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if outlets_for_client:
                final_outlet = st.sidebar.selectbox("🏠 Select Outlet", outlets_for_client)
            else:
                st.sidebar.warning(f"No outlets found for branch '{final_client}'")
                final_outlet = "None"
                
        # Cash is usually tracked at the Outlet level, but we display location routing just in case
        raw_loc = str(assigned_location).strip().title()
        if raw_loc.lower() != 'all':
            st.sidebar.markdown(f"**📍 Location:** {raw_loc}")

        # ==========================================
        # 3. CASH ENTRY UI (LIVE MATH)
        # ==========================================
        st.info(f"📝 Entering Cash Report for **{final_outlet}**")
        
        # We don't use st.form here so the math updates LIVE while they type
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("📅 Report Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
            m_reading = st.number_input("Main Reading", min_value=0.0, step=100.0)
            cash_val = st.number_input("Cash in Drawer", min_value=0.0, step=100.0)
            visa_val = st.number_input("Visa / Card", min_value=0.0, step=100.0)
            
        with col2:
            st.write("###") # Spacing
            exp_val = st.number_input("Expenses (Petty Cash)", min_value=0.0, step=100.0)
            on_acc_val = st.number_input("On Account / Credit", min_value=0.0, step=100.0)

        # Auto-Calculating the math
        revenue = cash_val + visa_val + exp_val + on_acc_val
        over_short = revenue - m_reading
        
        st.divider()
        
        # Live Metrics
        c1, c2 = st.columns(2)
        c1.metric("Total Revenue", f"{revenue:,.2f}")
        c2.metric("Over / Short", f"{over_short:,.2f}", delta=f"{over_short:,.2f}", delta_color="normal")

        # ==========================================
        # 4. SUBMIT DATA
        # ==========================================
        if st.button("🚀 SUBMIT DAILY REPORT", type="primary", use_container_width=True):
            if final_outlet == "None":
                st.error("❌ Cannot submit without a valid outlet.")
            else:
                submission_data = {
                    "date": str(entry_date), 
                    "client_name": final_client,
                    "outlet": final_outlet,
                    "main_reading": m_reading, 
                    "cash": cash_val, 
                    "visa": visa_val, 
                    "expenses": exp_val, 
                    "on_account": on_acc_val,
                    "revenue": revenue,
                    "over_short": over_short, 
                    "reported_by": user
                }
                
                try:
                    # Make sure your Supabase table is named 'daily_cash'
                    supabase.table("daily_cash").insert([submission_data]).execute()
                    st.success(f"✅ Data saved securely for {final_outlet}! Variance: {over_short:,.2f}")
                    # Optional: Add st.balloons() here for a fun UI touch when they submit perfectly
                except Exception as e:
                    st.error(f"❌ Database Error: {e}. Please check your Supabase table columns.")

    except Exception as e:
        st.error(f"❌ System Error: {e}")