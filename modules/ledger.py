import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
import streamlit.components.v1 as components
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_ledger(user, role):
    supabase = get_supabase()
    
    # Initialize the lock for the Save button
    if 'ledger_is_saving' not in st.session_state:
        st.session_state.ledger_is_saving = False

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
        query = supabase.table("ledger_logs").select("*")
        if client_name != "All": query = query.eq("client_name", client_name)
        if outlet != "All": query = query.eq("outlet", outlet)
            
        logs_res = query.execute()
        df_logs = pd.DataFrame(logs_res.data) if logs_res.data else pd.DataFrame()
        
        cat_query = supabase.table("ledger_categories").select("category_name")
        if client_name != "All": cat_query = cat_query.eq("client_name", client_name)
        cat_res = cat_query.execute()
        categories = sorted([r['category_name'] for r in cat_res.data]) if cat_res.data else []
        
        ent_query = supabase.table("ledger_entities").select("entity_name")
        if client_name != "All": ent_query = ent_query.eq("client_name", client_name)
        ent_res = ent_query.execute()
        entities = sorted([r['entity_name'] for r in ent_res.data]) if ent_res.data else []
        
    except Exception as e:
        st.error(f"❌ Error fetching database records: {e}")
        return

    # --- 📊 LIVE BALANCE DASHBOARD ---
    if not df_logs.empty:
        df_logs['credit'] = pd.to_numeric(df_logs['credit']).fillna(0)
        df_logs['debit'] = pd.to_numeric(df_logs['debit']).fillna(0)
        
        total_credit = df_logs['credit'].sum()
        total_debit = df_logs['debit'].sum()
        net_balance = total_credit - total_debit
        
        st.markdown("#### 💰 Global Portfolio Balance")
        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 Total Taken (Credit)", f"${total_credit:,.2f}")
        m2.metric("🟢 Total Paid (Debit)", f"${total_debit:,.2f}")
        
        if net_balance > 0:
            m3.metric("⚖️ Net Outstanding", f"${net_balance:,.2f}", "Owed to Business", delta_color="inverse")
        elif net_balance < 0:
            m3.metric("⚖️ Net Outstanding", f"${abs(net_balance):,.2f}", "Owed by Business", delta_color="normal")
        else:
            m3.metric("⚖️ Net Outstanding", "$0.00", "Perfectly Settled")

        with st.expander("🔍 View Individual Breakdown", expanded=False):
            summary_df = df_logs.groupby('entity_name')[['credit', 'debit']].sum().reset_index()
            summary_df['remaining'] = summary_df['credit'] - summary_df['debit']
            active_debts = summary_df[summary_df['remaining'] != 0].copy()
            
            if active_debts.empty:
                st.success("🎉 All individual accounts are perfectly balanced!")
            else:
                active_debts['Status'] = active_debts['remaining'].apply(lambda x: "🔴 Owed to Business" if x > 0 else "🟢 Owed by Business")
                active_debts['Balance'] = active_debts['remaining'].abs().apply(lambda x: f"${x:,.2f}")
                display_summary = active_debts[['entity_name', 'Balance', 'Status']].sort_values(by='Status', ascending=False)
                display_summary.columns = ['👤 Debt in Charge', '💵 Outstanding Amount', '📌 Status']
                st.dataframe(display_summary, use_container_width=True, hide_index=True)
    else:
        st.info("No financial records found yet.")

    st.divider()

    # ==========================================
    # 2. THE TABS
    # ==========================================
    tab_new, tab_history, tab_statement, tab_import = st.tabs(["➕ Add New", "🗂️ History & Edit", "📄 Statement", "📥 Import Excel"])

    with tab_new:
        if user_role == "viewer":
            st.warning("👀 Viewers cannot add transactions.")
        else:
            with st.container(border=True):
                st.markdown("#### 📝 Record Entry")
                today_local = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
                t_date = st.date_input("📅 Transaction Date", value=today_local)
                
                col1, col2 = st.columns(2)
                with col1:
                    cat_options = categories + ["➕ Add New Category..."]
                    selected_cat = st.selectbox("📂 Category", cat_options, key="cat_sel")
                    final_cat = st.text_input("✨ Type New Category:", key="cat_new") if selected_cat == "➕ Add New Category..." else selected_cat
                
                with col2:
                    ent_options = entities + ["➕ Add New Debt in Charge..."]
                    selected_ent = st.selectbox("👤 Debt in Charge", ent_options, key="ent_sel")
                    final_ent = st.text_input("✨ Type New Name:", key="ent_new") if selected_ent == "➕ Add New Debt in Charge..." else selected_ent
                
                t_desc = st.text_area("📝 Description", placeholder="e.g., Personnel for the Boss", key="t_desc")
                
                col3, col4 = st.columns(2)
                with col3:
                    t_credit = st.number_input("🔴 CREDIT (Taken)", min_value=0.0, step=1.0, key="t_credit")
                with col4:
                    t_debit = st.number_input("🟢 DEBIT (Paid)", min_value=0.0, step=1.0, key="t_debit")

                st.write("")
                if st.button("💾 Save Transaction", type="primary", use_container_width=True, disabled=st.session_state.ledger_is_saving):
                    if not final_cat or not final_ent or (t_credit == 0 and t_debit == 0):
                        st.error("❌ Please fill out Category, Debt in Charge, and at least one Amount.")
                    else:
                        st.session_state.ledger_is_saving = True
                        with st.spinner("Saving..."):
                            try:
                                clean_cat, clean_ent = final_cat.strip().title(), final_ent.strip().title()
                                if clean_cat not in categories:
                                    supabase.table("ledger_categories").insert({"category_name": clean_cat, "client_name": client_name}).execute()
                                if clean_ent not in entities:
                                    supabase.table("ledger_entities").insert({"entity_name": clean_ent, "client_name": client_name}).execute()
                                
                                new_log = {
                                    "date": str(t_date), "category": clean_cat, "entity_name": clean_ent,
                                    "description": t_desc.strip(), "credit": t_credit, "debit": t_debit,
                                    "logged_by": user, "client_name": client_name, "outlet": outlet
                                }
                                supabase.table("ledger_logs").insert([new_log]).execute()
                                st.success("✅ Saved!")
                                st.session_state.ledger_is_saving = False
                                st.rerun()
                            except Exception as e:
                                st.session_state.ledger_is_saving = False
                                st.error(f"❌ Error: {e}")

    with tab_history:
        st.markdown("#### 🗂️ History & Editor")
        if not df_logs.empty:
            st.info("💡 **Double-click any cell to edit.**")
            df_logs = df_logs.sort_values(by="date", ascending=False)
            filter_ent = st.selectbox("🔍 Filter by Entity:", ["All"] + entities, key="hist_filter")
            
            edit_df = df_logs.copy()
            if filter_ent != "All":
                edit_df = edit_df[edit_df['entity_name'] == filter_ent]
            
            cols_to_show = ['id', 'date', 'entity_name', 'category', 'description', 'credit', 'debit']
            edited_data = st.data_editor(edit_df[cols_to_show], use_container_width=True, disabled=["id"], hide_index=True, key="ledger_editor")
            
            if st.button("💾 Save Edits to History", type="primary"):
                if user_role == "viewer":
                    st.error("🚫 Access Denied.")
                else:
                    with st.spinner("Updating..."):
                        updates = 0
                        safe_edited = edited_data.fillna('')
                        safe_orig = edit_df[cols_to_show].fillna('')
                        for index, new_row in safe_edited.iterrows():
                            if new_row.to_dict() != safe_orig.loc[index].to_dict():
                                update_payload = {
                                    "date": str(new_row['date']), "entity_name": str(new_row['entity_name']),
                                    "category": str(new_row['category']), "description": str(new_row['description']),
                                    "credit": float(new_row['credit']), "debit": float(new_row['debit'])
                                }
                                supabase.table("ledger_logs").update(update_payload).eq("id", new_row['id']).execute()
                                updates += 1
                        if updates > 0:
                            st.success(f"✅ Updated {updates} record(s)!")
                            st.rerun()

    with tab_statement:
        st.markdown("#### 📄 Generate Official Statement")
        if entities:
            target_ent = st.selectbox("👤 Select Entity:", entities, key="stmt_target")
            if st.button("🚀 Generate Statement", type="primary"):
                target_df = df_logs[df_logs['entity_name'] == target_ent].copy().sort_values(by="date")
                if not target_df.empty:
                    balance = target_df['credit'].sum() - target_df['debit'].sum()
                    bal_style = "color: #d9534f;" if balance > 0 else "color: #5cb85c;"
                    bal_text = f"<span style='{bal_style}'>${abs(balance):,.2f} ({'Owed to Biz' if balance > 0 else 'Owed by Biz' if balance < 0 else 'Settled'})</span>"
                    
                    rows_html = ""
                    for _, row in target_df.iterrows():
                        rows_html += f"<tr><td>{str(row['date'])[:10]}</td><td>{row['category']}</td><td>{row['description']}</td><td style='text-align:right;'>${row['credit']:,.2f}</td><td style='text-align:right;'>${row['debit']:,.2f}</td></tr>"

                    html_content = f"""
                    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                        <h2 style="text-align:center;">STATEMENT OF ACCOUNT</h2>
                        <p><strong>Issued To:</strong> {target_ent} | <strong>Balance:</strong> {bal_text}</p>
                        <table style="width:100%; border-collapse: collapse;">
                            <tr style="background:#f8f9fa;"><th>Date</th><th>Category</th><th>Description</th><th>Credit</th><th>Debit</th></tr>
                            {rows_html}
                        </table>
                        <br><button onclick="window.print()" style="padding:10px; background:#007bff; color:white; border:none; border-radius:5px; cursor:pointer;">🖨️ Print Statement</button>
                    </div>
                    """
                    components.html(html_content, height=600, scrolling=True)

    with tab_import:
        st.markdown("#### 📥 Import Historical Data")
        uploaded_file = st.file_uploader("Upload Excel/CSV", type=["csv", "xlsx"])
        if uploaded_file:
            try:
                df_import = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df_import.columns = [str(c).strip().lower().replace(" ", "_") for c in df_import.columns]
                required = ['date', 'category', 'debt_in_charge', 'description', 'credit', 'debit']
                if not all(col in df_import.columns for col in required):
                    st.error(f"❌ Missing columns. Required: {required}")
                else:
                    st.dataframe(df_import.head(5))
                    if st.button("🚀 Run Import", type="primary"):
                        with st.spinner("Processing..."):
                            records = []
                            df_import = df_import.fillna(0)
                            for _, row in df_import.iterrows():
                                cat = str(row['category']).strip().title()
                                ent = str(row['debt_in_charge']).strip().title()
                                records.append({
                                    "date": str(row['date'])[:10], "category": cat, "entity_name": ent,
                                    "description": str(row['description']) if str(row['description']) != '0' else "",
                                    "credit": float(row['credit']), "debit": float(row['debit']),
                                    "logged_by": f"{user} (Import)", "client_name": client_name, "outlet": outlet
                                })
                            for i in range(0, len(records), 500):
                                supabase.table("ledger_logs").insert(records[i:i + 500]).execute()
                            st.success(f"✅ Imported {len(records)} records!")
                            st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")