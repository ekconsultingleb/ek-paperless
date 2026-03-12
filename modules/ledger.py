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

def render_ledger(conn, sheet_link, user, role):
    supabase = get_supabase()
    
    if 'ledger_is_saving' not in st.session_state:
        st.session_state.ledger_is_saving = False

    client_name = st.session_state.get('client_name', 'Unknown')
    outlet = st.session_state.get('assigned_outlet', 'Unknown')
    user_role = str(role).lower()

    if user_role not in ["manager", "admin", "admin_all", "viewer"]:
        st.error("🚫 Access Denied.")
        return

    st.markdown("### 💸 Cash & Debt Control")
    
    # ==========================================
    # 1. FETCH DATA & SELECTIVE MAPPING
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

        category_mapping = {}
        if not df_logs.empty:
            for cat in categories:
                relevant_entities = df_logs[df_logs['category'] == cat]['entity_name'].unique().tolist()
                category_mapping[cat] = sorted(relevant_entities)
        
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return

    # --- 📊 LIVE BALANCE DASHBOARD ---
    if not df_logs.empty:
        df_logs['credit'] = pd.to_numeric(df_logs['credit']).fillna(0)
        df_logs['debit'] = pd.to_numeric(df_logs['debit']).fillna(0)
        total_credit, total_debit = df_logs['credit'].sum(), df_logs['debit'].sum()
        net_balance = total_credit - total_debit
        
        st.markdown("#### 💰 Global Portfolio Balance")
        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 Total Taken", f"${total_credit:,.2f}")
        m2.metric("🟢 Total Paid", f"${total_debit:,.2f}")
        m3.metric("⚖️ Net Outstanding", f"${abs(net_balance):,.2f}", 
                  "Owed to Business" if net_balance > 0 else "Owed by Business", 
                  delta_color="inverse" if net_balance > 0 else "normal")

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
                t_date = st.date_input("📅 Date", value=datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date())
                
                col1, col2 = st.columns(2)
                with col1:
                    sel_cat = st.selectbox("📂 Category", categories + ["➕ Add New Category..."], key="cat_sel")
                    fin_cat = st.text_input("✨ New Category Name:", key="cat_new") if sel_cat == "➕ Add New Category..." else sel_cat
                with col2:
                    rel_ents = category_mapping.get(sel_cat, [])
                    sel_ent = st.selectbox("👤 Debt in Charge", rel_ents + ["➕ Add New Debt in Charge..."], key="ent_sel")
                    fin_ent = st.text_input("✨ New Name:", key="ent_new") if sel_ent == "➕ Add New Debt in Charge..." else sel_ent
                
                t_desc = st.text_area("📝 Description", key="t_desc")
                c3, c4 = st.columns(2)
                with c3: t_credit = st.number_input("🔴 CREDIT", min_value=0.0, step=1.0, key="t_credit")
                with c4: t_debit = st.number_input("🟢 DEBIT", min_value=0.0, step=1.0, key="t_debit")

                if st.button("💾 Save Transaction", type="primary", use_container_width=True, disabled=st.session_state.ledger_is_saving):
                    st.session_state.ledger_is_saving = True
                    try:
                        clean_cat, clean_ent = fin_cat.strip().title(), fin_ent.strip().title()
                        if clean_cat not in categories:
                            supabase.table("ledger_categories").insert({"category_name": clean_cat, "client_name": client_name}).execute()
                        
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
        if not df_logs.empty:
            df_hist = df_logs.sort_values(by="date", ascending=False)
            cols = ['id', 'date', 'entity_name', 'category', 'description', 'credit', 'debit']
            edited_data = st.data_editor(df_hist[cols], use_container_width=True, disabled=["id"], hide_index=True, key="ledger_history_editor")
            
            if st.button("💾 Save History Edits", type="primary"):
                with st.spinner("Updating records..."):
                    updates = 0
                    safe_edited = edited_data.fillna('')
                    safe_orig = df_hist[cols].fillna('')
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
                        st.success(f"✅ Updated {updates} records!")
                        st.rerun()

    with tab_statement:
        st.markdown("#### 📄 Account Statement")
        entities = sorted(df_logs['entity_name'].unique().tolist()) if not df_logs.empty else []
        if entities:
            target_ent = st.selectbox("👤 Select Person:", entities, key="stmt_target")
            if st.button("🚀 Generate Statement", type="primary"):
                target_df = df_logs[df_logs['entity_name'] == target_ent].copy().sort_values(by="date")
                balance = target_df['credit'].sum() - target_df['debit'].sum()
                
                rows_html = "".join([f"""
                    <tr>
                        <td style="padding: 12px; border-bottom: 1px solid #eee;">{str(r['date'])[:10]}</td>
                        <td style="padding: 12px; border-bottom: 1px solid #eee;">{r['category']}</td>
                        <td style="padding: 12px; border-bottom: 1px solid #eee;">{r['description']}</td>
                        <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; color: #d9534f;">${r['credit']:,.2f}</td>
                        <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right; color: #5cb85c;">${r['debit']:,.2f}</td>
                    </tr>""" for _, r in target_df.iterrows()])

                html_content = f"""
                <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background-color: white; color: #333; border-radius: 15px; border: 1px solid #e0e0e0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #333; padding-bottom: 20px; margin-bottom: 30px;">
                        <div>
                            <h1 style="margin: 0; color: #1a1a1a; font-size: 28px;">STATEMENT OF ACCOUNT</h1>
                            <p style="margin: 5px 0; color: #666;">EK Consulting Partner Portal</p>
                        </div>
                        <div style="text-align: right;">
                            <p style="margin: 0; color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">Outstanding Balance</p>
                            <h2 style="margin: 0; color: {'#d9534f' if balance > 0 else '#5cb85c'}; font-size: 32px;">${abs(balance):,.2f}</h2>
                            <p style="margin: 0; font-size: 12px; color: #666;">{'Owed to Business' if balance > 0 else 'Owed by Business'}</p>
                        </div>
                    </div>
                    
                    <p style="font-size: 16px; margin-bottom: 20px;"><strong>Account Name:</strong> {target_ent}</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                        <thead>
                            <tr style="background-color: #f9f9f9; border-bottom: 2px solid #ddd;">
                                <th style="padding: 12px; text-align: left; font-size: 13px; text-transform: uppercase; color: #666;">Date</th>
                                <th style="padding: 12px; text-align: left; font-size: 13px; text-transform: uppercase; color: #666;">Category</th>
                                <th style="padding: 12px; text-align: left; font-size: 13px; text-transform: uppercase; color: #666;">Description</th>
                                <th style="padding: 12px; text-align: right; font-size: 13px; text-transform: uppercase; color: #666;">Credit (+)</th>
                                <th style="padding: 12px; text-align: right; font-size: 13px; text-transform: uppercase; color: #666;">Debit (-)</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                    
                    <div style="margin-top: 40px; text-align: center;">
                        <button onclick="window.print()" style="padding: 12px 30px; background-color: #333; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer;">🖨️ Print or Save as PDF</button>
                    </div>
                </div>
                """
                components.html(html_content, height=800, scrolling=True)

    with tab_import:
        st.markdown("#### 📥 Import Data")
        uploaded_file = st.file_uploader("Upload Excel/CSV", type=["csv", "xlsx"])
        if uploaded_file:
            df_import = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            df_import.columns = [str(c).strip().lower().replace(" ", "_") for c in df_import.columns]
            if st.button("🚀 Run Import"):
                records = []
                for _, row in df_import.fillna(0).iterrows():
                    records.append({
                        "date": str(row['date'])[:10], "category": str(row['category']).title(), 
                        "entity_name": str(row['debt_in_charge']).title(), "description": str(row['description']),
                        "credit": float(row['credit']), "debit": float(row['debit']),
                        "logged_by": f"{user} (Import)", "client_name": client_name, "outlet": outlet
                    })
                for i in range(0, len(records), 500):
                    supabase.table("ledger_logs").insert(records[i:i + 500]).execute()
                st.success("✅ Import Complete!")
                st.rerun()