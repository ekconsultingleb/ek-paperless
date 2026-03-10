import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_ledger(conn, sheet_link, user, role):
    supabase = get_supabase()
    
    # Grab the user's routing info from the session
    client_name = st.session_state.get('client_name', 'Unknown')
    outlet = st.session_state.get('assigned_outlet', 'Unknown')
    user_role = str(role).lower()

    # 🚦 TRAFFIC COP: Who sees what?
    if user_role not in ["manager", "admin", "admin_all", "viewer"]:
        st.error("🚫 Access Denied. Only authorized personnel can view financials.")
        return

    st.markdown("### 💸 Cash & Debt Control")
    
    # ==========================================
    # 1. FETCH DATA & CALCULATE LIVE BALANCES
    # ==========================================
    try:
        # Fetch Logs
        query = supabase.table("ledger_logs").select("*")
        if client_name != "All":
            query = query.eq("client_name", client_name)
        if outlet != "All":
            query = query.eq("outlet", outlet)
            
        logs_res = query.execute()
        df_logs = pd.DataFrame(logs_res.data) if logs_res.data else pd.DataFrame()
        
        # Fetch Categories
        cat_query = supabase.table("ledger_categories").select("category_name")
        if client_name != "All": cat_query = cat_query.eq("client_name", client_name)
        cat_res = cat_query.execute()
        categories = sorted([r['category_name'] for r in cat_res.data]) if cat_res.data else []
        
        # Fetch Entities (Debt in Charge)
        ent_query = supabase.table("ledger_entities").select("entity_name")
        if client_name != "All": ent_query = ent_query.eq("client_name", client_name)
        ent_res = ent_query.execute()
        entities = sorted([r['entity_name'] for r in ent_res.data]) if ent_res.data else []
        
    except Exception as e:
        st.error(f"❌ Error fetching database records: {e}")
        return

    # --- 📊 LIVE BALANCE DASHBOARD ---
    st.markdown("#### ⚖️ Outstanding Balances Summary")
    
    if not df_logs.empty:
        # Fill missing numbers with 0 so the math doesn't break
        df_logs['credit'] = pd.to_numeric(df_logs['credit']).fillna(0)
        df_logs['debit'] = pd.to_numeric(df_logs['debit']).fillna(0)
        
        # Group by the person/entity and calculate Remaining = Credit - Debit
        summary_df = df_logs.groupby('entity_name')[['credit', 'debit']].sum().reset_index()
        summary_df['remaining'] = summary_df['credit'] - summary_df['debit']
        
        # Filter out people who have a $0 balance (debt fully paid)
        active_debts = summary_df[summary_df['remaining'] != 0].sort_values(by='remaining', ascending=False)
        
        if active_debts.empty:
            st.success("🎉 All accounts are perfectly balanced at $0.00!")
        else:
            # Create a scrolling row of metric cards
            cols = st.columns(min(len(active_debts), 4))
            for idx, row in active_debts.iterrows():
                col_idx = idx % 4
                entity = row['entity_name']
                remaining = row['remaining']
                
                # Format: Red if they owe us (Credit > Debit), Green if we owe them
                if remaining > 0:
                    cols[col_idx].metric(label=f"👤 {entity}", value=f"${remaining:,.2f}", delta="Owed to Business", delta_color="inverse")
                else:
                    cols[col_idx].metric(label=f"👤 {entity}", value=f"${abs(remaining):,.2f}", delta="Owed by Business", delta_color="normal")
    else:
        st.info("No financial records found yet. Start adding transactions below!")

    st.divider()

    # ==========================================
    # 2. THE TABS (Add Transaction & View Ledger)
    # ==========================================
    tab_new, tab_history = st.tabs(["➕ Add New Transaction", "🗂️ Ledger History"])

    # --- TAB 1: ADD NEW TRANSACTION ---
    with tab_new:
        if user_role == "viewer":
            st.warning("👀 Viewers cannot add new transactions.")
        else:
            with st.container(border=True):
                st.markdown("#### 📝 Record Entry")
                today_local = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
                
                # We do NOT use st.form here because we need the dynamic dropdowns to appear instantly!
                t_date = st.date_input("📅 Transaction Date", value=today_local)
                
                col1, col2 = st.columns(2)
                with col1:
                    # SMART CATEGORY SELECTOR
                    cat_options = categories + ["➕ Add New Category..."]
                    selected_cat = st.selectbox("📂 Category", cat_options)
                    if selected_cat == "➕ Add New Category...":
                        final_cat = st.text_input("✨ Type New Category Name:")
                    else:
                        final_cat = selected_cat
                        
                with col2:
                    # SMART ENTITY SELECTOR
                    ent_options = entities + ["➕ Add New Debt in Charge..."]
                    selected_ent = st.selectbox("👤 Debt in Charge", ent_options)
                    if selected_ent == "➕ Add New Debt in Charge...":
                        final_ent = st.text_input("✨ Type New Person/Company Name:")
                    else:
                        final_ent = selected_ent
                        
                t_desc = st.text_area("📝 Description", placeholder="e.g., Mr. Doumit paid for school fees...")
                
                col3, col4 = st.columns(2)
                with col3:
                    t_credit = st.number_input("🔴 CREDIT (Money taken out / Owed to business)", min_value=0.0, step=0.01, format="%.2f")
                with col4:
                    t_debit = st.number_input("🟢 DEBIT (Money paid back / Returned to business)", min_value=0.0, step=0.01, format="%.2f")

                st.write("") # Spacer
                if st.button("💾 Save Transaction", type="primary", use_container_width=True):
                    if not final_cat:
                        st.error("❌ Please provide a Category.")
                    elif not final_ent:
                        st.error("❌ Please provide a Debt in Charge.")
                    elif t_credit == 0 and t_debit == 0:
                        st.error("❌ Please enter an amount in either Credit or Debit.")
                    else:
                        with st.spinner("Saving..."):
                            clean_cat = final_cat.strip().title()
                            clean_ent = final_ent.strip().title()
                            
                            # 1. Save new Category if needed
                            if clean_cat not in categories:
                                supabase.table("ledger_categories").insert({"category_name": clean_cat, "client_name": client_name}).execute()
                            
                            # 2. Save new Entity if needed
                            if clean_ent not in entities:
                                supabase.table("ledger_entities").insert({"entity_name": clean_ent, "client_name": client_name}).execute()
                                
                            # 3. Save the Transaction Log
                            new_log = {
                                "date": str(t_date),
                                "category": clean_cat,
                                "entity_name": clean_ent,
                                "description": t_desc.strip(),
                                "credit": t_credit,
                                "debit": t_debit,
                                "logged_by": user,
                                "client_name": client_name,
                                "outlet": outlet
                            }
                            supabase.table("ledger_logs").insert([new_log]).execute()
                            
                            st.success("✅ Transaction saved successfully!")
                            st.rerun()

    # --- TAB 2: LEDGER HISTORY ---
    with tab_history:
        st.markdown("#### 🗂️ Transaction History")
        
        if df_logs.empty:
            st.info("No transactions found.")
        else:
            # Sort by date (newest first)
            df_logs = df_logs.sort_values(by="date", ascending=False)
            
            # Simple Filter
            filter_ent = st.selectbox("🔍 Filter by Debt in Charge:", ["All"] + entities, key="hist_filter")
            
            display_df = df_logs.copy()
            if filter_ent != "All":
                display_df = display_df[display_df['entity_name'] == filter_ent]
                
            # Clean up the dataframe for display
            display_df = display_df[['date', 'entity_name', 'category', 'description', 'credit', 'debit', 'logged_by']]
            display_df.columns = ['Date', 'Debt in Charge', 'Category', 'Description', 'Credit ($)', 'Debit ($)', 'Logged By']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)