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
                    query = query.eq("client_name", str(assigned_client).strip())
                    
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
        # REPORT SECTION
        # ==========================================
        with st.expander("📊 Cash Report & Export", expanded=False):
            today_r = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start_r = today_r - timedelta(days=30)
            date_range_r = st.date_input("📅 Date Range", value=(default_start_r, today_r),
                                         max_value=today_r, key="cash_rep_dates")
            if len(date_range_r) == 2:
                start_r, end_r = date_range_r
                rep_q = (supabase.table("daily_cash").select("*")
                         .gte("date", str(start_r))
                         .lte("date", str(end_r))
                         .order("date", desc=True)
                         .limit(5000)
                         .execute())
                df_rep = pd.DataFrame(rep_q.data) if rep_q.data else pd.DataFrame()

                if not df_rep.empty:
                    if final_client.lower() not in ["all", "", "none"]:
                        df_rep = df_rep[df_rep["client_name"].str.lower() == final_client.lower()]
                    if final_outlet.lower() not in ["all", "none", ""]:
                        df_rep = df_rep[df_rep["outlet"].str.lower() == final_outlet.lower()]

                if df_rep.empty:
                    st.info("No cash reports found for the selected period.")
                else:
                    currency_cols = ["main_reading", "cash", "visa", "expenses", "on_account", "revenue", "over_short"]
                    df_display = df_rep.copy()
                    for col in currency_cols:
                        if col in df_display.columns:
                            df_display[col] = pd.to_numeric(df_display[col], errors="coerce").fillna(0)

                    totals = {c: df_display[c].sum() for c in currency_cols if c in df_display.columns}
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    st.caption(f"{len(df_display)} entries · Revenue total: **${totals.get('revenue', 0):,.2f}** · Over/Short: **${totals.get('over_short', 0):,.2f}**")

                    csv_bytes = df_rep.to_csv(index=False).encode("utf-8-sig")
                    st.download_button("⬇️ Download CSV", data=csv_bytes,
                                       file_name=f"DailyCash_{start_r}_{end_r}.csv",
                                       mime="text/csv", type="primary", use_container_width=True)
            else:
                st.info("Select both a start and end date.")

        st.divider()

        # ==========================================
        # 3. CASH ENTRY UI (LIVE MATH)
        # ==========================================
        st.info(f"📝 Entering Cash Report for **{final_outlet}**")
        
        # We don't use st.form here so the math updates LIVE while they type
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("📅 Report Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
            m_reading = st.number_input("Main Reading", min_value=0.0, step=100.0, format="%g")
            cash_val = st.number_input("Cash in Drawer", min_value=0.0, step=100.0, format="%g")
            visa_val = st.number_input("Visa / Card", min_value=0.0, step=100.0, format="%g")

        with col2:
            st.write("###") # Spacing
            exp_val = st.number_input("Expenses (Petty Cash)", min_value=0.0, step=100.0, format="%g")
            on_acc_val = st.number_input("On Account / Credit", min_value=0.0, step=100.0, format="%g")

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
        # Duplicate confirmation state
        if 'cash_confirm_dup' not in st.session_state:
            st.session_state['cash_confirm_dup'] = False

        if st.session_state.get('cash_confirm_dup'):
            st.warning(f"⚠️ A cash report already exists for **{final_outlet}** on **{entry_date}**. Submit anyway?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Submit Anyway", type="primary", width="stretch"):
                    st.session_state['cash_confirm_dup'] = False
                    submission_data = {
                        "date": str(entry_date), "client_name": final_client, "outlet": final_outlet,
                        "main_reading": m_reading, "cash": cash_val, "visa": visa_val,
                        "expenses": exp_val, "on_account": on_acc_val,
                        "revenue": revenue, "over_short": over_short, "reported_by": user
                    }
                    try:
                        supabase.table("daily_cash").insert([submission_data]).execute()
                        st.success(f"✅ Data saved for {final_outlet}! Variance: {over_short:,.2f}")
                    except Exception as e:
                        st.error(f"❌ Database Error: {e}")
            with col_no:
                if st.button("Cancel", width="stretch"):
                    st.session_state['cash_confirm_dup'] = False
                    st.rerun()
        else:
            if st.button("🚀 SUBMIT DAILY REPORT", type="primary", width="stretch"):
                if final_outlet == "None" or final_client == "Select Branch":
                    st.error("❌ Cannot submit without a valid Branch and Outlet.")
                else:
                    submission_data = {
                        "date": str(entry_date), "client_name": final_client, "outlet": final_outlet,
                        "main_reading": m_reading, "cash": cash_val, "visa": visa_val,
                        "expenses": exp_val, "on_account": on_acc_val,
                        "revenue": revenue, "over_short": over_short, "reported_by": user
                    }
                    try:
                        # Check for duplicate before inserting
                        existing = supabase.table("daily_cash").select("id").eq("date", str(entry_date)).eq("outlet", final_outlet).execute()
                        if existing.data:
                            st.session_state['cash_confirm_dup'] = True
                            st.rerun()
                        else:
                            supabase.table("daily_cash").insert([submission_data]).execute()
                            st.success(f"✅ Data saved for {final_outlet}! Variance: {over_short:,.2f}")
                    except Exception as e:
                        st.error(f"❌ Database Error: {e}")

    except Exception as e:
        st.error(f"❌ System Error: {e}")