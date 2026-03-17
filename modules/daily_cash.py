import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from modules.nav_helper import build_outlet_location_sidebar

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
                    
                archive_res = query.order("date", desc=True).limit(2000).execute()
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
        # PRO TIP: Query the small users table for instant navigation
        final_client, final_outlet, final_location_sidebar = build_outlet_location_sidebar(
            assigned_client, assigned_outlet, assigned_location,
            outlet_key="cash_outlet", location_key="cash_location"
        )

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
            if final_outlet == "None" or final_client == "Select Branch":
                st.error("❌ Cannot submit without a valid Branch and Outlet.")
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
                    supabase.table("daily_cash").insert([submission_data]).execute()
                    st.success(f"✅ Data saved securely for {final_outlet}! Variance: {over_short:,.2f}")
                    # Optional: Add st.balloons() here for a fun UI touch when they submit perfectly
                except Exception as e:
                    st.error(f"❌ Database Error: {e}. Please check your Supabase table columns.")

    except Exception as e:
        st.error(f"❌ System Error: {e}")