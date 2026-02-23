import streamlit as st
import pandas as pd
from datetime import datetime

def render_daily_cash(conn, sheet_link, assigned_outlet):
    st.markdown(f"### 🏦 Daily Cash Report")
    try:
        # Load the cash ledger and the inventory catalog (to get the official outlet names)
        df_cash = conn.read(spreadsheet=sheet_link, worksheet="cash", ttl=0)
        df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory", ttl=600)
        
        # --- OUTLET SECURITY LOCK ---
        all_outlets = list(df_inv['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_inv.columns else ["Main"]
        if assigned_outlet.lower() != 'all' and assigned_outlet != '':
            allowed_outlets = [assigned_outlet]
        else:
            allowed_outlets = all_outlets
        
        with st.form("cash_entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                outlet_name = st.selectbox("🏢 Select Outlet", allowed_outlets)
                m_reading = st.number_input("Main Reading", min_value=0.0, step=0.1)
                cash_val = st.number_input("Cash", min_value=0.0, step=0.1)
                visa_val = st.number_input("Visa", min_value=0.0, step=0.1)
            with col2:
                exp_val = st.number_input("Expenses", min_value=0.0, step=0.1)
                on_acc_val = st.number_input("On Account", min_value=0.0, step=0.1)
                entry_date = st.date_input("📅 Report Date", datetime.now())

            # Auto-Calculating the math before submission!
            revenue = cash_val + visa_val + exp_val + on_acc_val
            over_short = revenue - m_reading
            
            st.divider()
            c1, c2 = st.columns(2)
            c1.metric("Total Revenue", f"{revenue:,.2f}")
            c2.metric("Over / Short", f"{over_short:,.2f}", delta=over_short)

            if st.form_submit_button("🚀 Submit Daily Report", type="primary", use_container_width=True):
                new_row = pd.DataFrame([{
                    "Date": entry_date.strftime("%Y-%m-%d"), 
                    "Outlet": outlet_name,
                    "Main Reading": m_reading, 
                    "Over / Short": over_short, 
                    "Revenue": revenue,
                    "Cash": cash_val, 
                    "Visa": visa_val, 
                    "Expenses": exp_val, 
                    "On Account": on_acc_val
                }])
                
                updated_cash = pd.concat([df_cash, new_row], ignore_index=True)
                conn.update(spreadsheet=sheet_link, worksheet="cash", data=updated_cash)
                st.success(f"✅ Data saved securely for {outlet_name}! Variance: {over_short:,.2f}")
                
    except Exception as e:
        st.error(f"Error loading Cash module: {e}")