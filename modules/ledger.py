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
    with st.expander("⚖️ Outstanding Balances Summary", expanded=True):
        if not df_logs.empty:
            df_logs['credit'] = pd.to_numeric(df_logs['credit']).fillna(0)
            df_logs['debit'] = pd.to_numeric(df_logs['debit']).fillna(0)
            
            summary_df = df_logs.groupby('entity_name')[['credit', 'debit']].sum().reset_index()
            summary_df['remaining'] = summary_df['credit'] - summary_df['debit']
            
            active_debts = summary_df[summary_df['remaining'] != 0].copy()
            
            if active_debts.empty:
                st.success("🎉 All accounts are perfectly balanced at $0.00!")
            else:
                active_debts['Status'] = active_debts['remaining'].apply(lambda x: "🔴 Owed to Business" if x > 0 else "🟢 Owed by Business")
                active_debts['Balance'] = active_debts['remaining'].abs().apply(lambda x: f"${x:,.2f}")
                
                display_summary = active_debts[['entity_name', 'Balance', 'Status']].sort_values(by='Status', ascending=False)
                display_summary.columns = ['👤 Debt in Charge', '💵 Outstanding Amount', '📌 Status']
                
                st.dataframe(display_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No financial records found yet. Start adding transactions below!")

    st.divider()

    # ==========================================
    # 2. THE TABS
    # ==========================================
    tab_new, tab_history, tab_statement, tab_import = st.tabs(["➕ Add New", "🗂️ History & Edit", "📄 Statement", "📥 Import Excel"])

    # --- TAB 1: ADD NEW TRANSACTION ---
    with tab_new:
        if user_role == "viewer":
            st.warning("👀 Viewers cannot add new transactions.")
        else:
            with st.container(border=True):
                st.markdown("#### 📝 Record Entry")
                today_local = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
                
                t_date = st.date_input("📅 Transaction Date", value=today_local)
                
                col1, col2 = st.columns(2)
                with col1:
                    cat_options = categories + ["➕ Add New Category..."]
                    selected_cat = st.selectbox("📂 Category", cat_options)
                    final_cat = st.text_input("✨ Type New Category Name:") if selected_cat == "➕ Add New Category..." else selected_cat
                        
                with col2:
                    ent_options = entities + ["➕ Add New Debt in Charge..."]
                    selected_ent = st.selectbox("👤 Debt in Charge", ent_options)
                    final_ent = st.text_input("✨ Type New Person/Company Name:") if selected_ent == "➕ Add New Debt in Charge..." else selected_ent
                        
                t_desc = st.text_area("📝 Description", placeholder="e.g., Mr. Doumit paid for school fees...")
                
                col3, col4 = st.columns(2)
                with col3:
                    t_credit = st.number_input("🔴 CREDIT (Money taken out / Owed to business)", min_value=0.0, step=1.0)
                with col4:
                    t_debit = st.number_input("🟢 DEBIT (Money paid back / Returned to business)", min_value=0.0, step=1.0)

                st.write("")
                if st.button("💾 Save Transaction", type="primary", use_container_width=True):
                    if not final_cat or not final_ent or (t_credit == 0 and t_debit == 0):
                        st.error("❌ Please fill out Category, Debt in Charge, and at least one Amount.")
                    else:
                        with st.spinner("Saving..."):
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
                            st.success("✅ Transaction saved!")
                            st.rerun()

    # --- TAB 2: HISTORY & EDIT (The Fix for Carole's Mistakes) ---
    with tab_history:
        st.markdown("#### 🗂️ Transaction History & Editor")
        if df_logs.empty:
            st.info("No transactions found.")
        else:
            st.info("💡 **Double-click any cell to edit a mistake.** Click 'Save Edits' at the bottom when finished.")
            
            df_logs = df_logs.sort_values(by="date", ascending=False)
            filter_ent = st.selectbox("🔍 Filter by Debt in Charge:", ["All"] + entities, key="hist_filter")
            
            edit_df = df_logs.copy()
            if filter_ent != "All":
                edit_df = edit_df[edit_df['entity_name'] == filter_ent]
                
            # Define what columns Carole is allowed to see and edit
            cols_to_show = ['id', 'date', 'entity_name', 'category', 'description', 'credit', 'debit']
            edit_df = edit_df[cols_to_show]
            
            # Display the interactive editor
            edited_data = st.data_editor(
                edit_df,
                use_container_width=True,
                disabled=["id"], # Protect the database ID!
                hide_index=True,
                key="ledger_editor"
            )
            
            if st.button("💾 Save Edits to History", type="primary"):
                if user_role == "viewer":
                    st.error("🚫 Viewers cannot edit records.")
                else:
                    with st.spinner("Updating database..."):
                        updates = 0
                        safe_edited = edited_data.fillna('')
                        safe_orig = edit_df.fillna('')
                        
                        for index, new_row in safe_edited.iterrows():
                            old_row = safe_orig.loc[index]
                            if new_row.to_dict() != old_row.to_dict():
                                row_id = new_row['id']
                                update_payload = {
                                    "date": str(new_row['date']),
                                    "entity_name": str(new_row['entity_name']),
                                    "category": str(new_row['category']),
                                    "description": str(new_row['description']),
                                    "credit": float(new_row['credit']) if new_row['credit'] else 0.0,
                                    "debit": float(new_row['debit']) if new_row['debit'] else 0.0
                                }
                                supabase.table("ledger_logs").update(update_payload).eq("id", row_id).execute()
                                updates += 1
                                
                        if updates > 0:
                            st.success(f"✅ Successfully updated {updates} record(s)!")
                            st.rerun()
                        else:
                            st.info("No changes were detected.")

    # --- TAB 3: GENERATE STATEMENT ---
    with tab_statement:
        st.markdown("#### 📄 Generate Official Statement")
        if not entities:
            st.warning("No entities found in the system yet.")
        else:
            target_ent = st.selectbox("👤 Select Person / Entity:", entities, key="stmt_target")
            
            if st.button("🚀 Generate Statement", type="primary"):
                target_df = df_logs[df_logs['entity_name'] == target_ent].copy()
                if target_df.empty:
                    st.warning(f"No transactions found for {target_ent}.")
                else:
                    target_df = target_df.sort_values(by="date", ascending=True)
                    
                    total_credit = target_df['credit'].sum()
                    total_debit = target_df['debit'].sum()
                    balance = total_credit - total_debit
                    
                    if balance > 0:
                        bal_text = f"<span style='color: #d9534f;'>${balance:,.2f} (Owed to Business)</span>"
                    elif balance < 0:
                        bal_text = f"<span style='color: #5cb85c;'>${abs(balance):,.2f} (Owed by Business)</span>"
                    else:
                        bal_text = f"<span>$0.00 (Settled)</span>"

                    rows_html = ""
                    for _, row in target_df.iterrows():
                        c_val = f"${row['credit']:,.2f}" if row['credit'] > 0 else "-"
                        d_val = f"${row['debit']:,.2f}" if row['debit'] > 0 else "-"
                        desc = row.get('description', '') or "<i>No description</i>"
                        
                        rows_html += f"""
                        <tr>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{str(row['date'])[:10]}</td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{row['category']}</td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd;'>{desc}</td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right; color: #d9534f;'>{c_val}</td>
                            <td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right; color: #5cb85c;'>{d_val}</td>
                        </tr>
                        """

                    html_content = f"""
                    <div id="printArea" style="font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: auto; border: 1px solid #eee; border-radius: 10px; background-color: #fff; color: #333;">
                        <div style="text-align: center; margin-bottom: 20px;">
                            <h2 style="margin: 0;">STATEMENT OF ACCOUNT</h2>
                            <p style="margin: 5px 0; color: #777;">{client_name if client_name != 'All' else 'EK Consulting Portal'}</p>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px;">
                            <div>
                                <strong>Issued To:</strong> {target_ent}<br>
                                <strong>Date Generated:</strong> {datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime('%Y-%m-%d')}
                            </div>
                            <div style="text-align: right; font-size: 18px;">
                                <strong>Final Balance:</strong> {bal_text}
                            </div>
                        </div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                            <thead>
                                <tr style="background-color: #f8f9fa;">
                                    <th style="padding: 10px; border-bottom: 2px solid #ddd; text-align: left;">Date</th>
                                    <th style="padding: 10px; border-bottom: 2px solid #ddd; text-align: left;">Category</th>
                                    <th style="padding: 10px; border-bottom: 2px solid #ddd; text-align: left;">Description</th>
                                    <th style="padding: 10px; border-bottom: 2px solid #ddd; text-align: right;">Credit (Taken)</th>
                                    <th style="padding: 10px; border-bottom: 2px solid #ddd; text-align: right;">Debit (Paid)</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                        <div style="text-align: center; margin-top: 30px;">
                            <button onclick="window.print()" style="background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer;">
                                🖨️ Print / Save as PDF
                            </button>
                        </div>
                    </div>
                    """
                    st.divider()
                    components.html(html_content, height=600, scrolling=True)

    # --- TAB 4: BULK EXCEL IMPORT ---
    with tab_import:
        st.markdown("#### 📥 Import Historical Data")
        st.info("Upload your old Excel or CSV file here to instantly populate the app.")
        
        st.markdown("""
        **⚠️ Required Column Names in your Excel file:**
        `Date` | `Category` | `Debt in Charge` | `Description` | `Credit` | `Debit`
        """)
        
        uploaded_file = st.file_uploader("Upload Excel/CSV", type=["csv", "xlsx"])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_import = pd.read_csv(uploaded_file)
                else:
                    df_import = pd.read_excel(uploaded_file)
                
                # Normalize column names for easy matching
                df_import.columns = [str(c).strip().lower().replace(" ", "_") for c in df_import.columns]
                
                # Check for required columns
                required = ['date', 'category', 'debt_in_charge', 'description', 'credit', 'debit']
                missing = [col for col in required if col not in df_import.columns]
                
                if missing:
                    st.error(f"❌ Missing required columns in your file: {', '.join(missing)}")
                else:
                    st.dataframe(df_import.head(5), use_container_width=True)
                    
                    if st.button("🚀 Run Import", type="primary"):
                        with st.spinner("Importing data and creating profiles..."):
                            records = []
                            new_categories = set()
                            new_entities = set()
                            
                            df_import = df_import.fillna(0) # Fill empty numbers with 0
                            
                            for _, row in df_import.iterrows():
                                cat = str(row['category']).strip().title()
                                ent = str(row['debt_in_charge']).strip().title()
                                
                                new_categories.add(cat)
                                new_entities.add(ent)
                                
                                records.append({
                                    "date": str(row['date'])[:10],
                                    "category": cat,
                                    "entity_name": ent,
                                    "description": str(row['description']) if str(row['description']) != '0' else "",
                                    "credit": float(row['credit']),
                                    "debit": float(row['debit']),
                                    "logged_by": f"{user} (Import)",
                                    "client_name": client_name,
                                    "outlet": outlet
                                })
                            
                            # 1. Save new categories
                            cats_to_insert = [{"category_name": c, "client_name": client_name} for c in new_categories if c not in categories]
                            if cats_to_insert: supabase.table("ledger_categories").insert(cats_to_insert).execute()
                            
                            # 2. Save new entities
                            ents_to_insert = [{"entity_name": e, "client_name": client_name} for e in new_entities if e not in entities]
                            if ents_to_insert: supabase.table("ledger_entities").insert(ents_to_insert).execute()
                            
                            # 3. Save logs in chunks to prevent timeout
                            for i in range(0, len(records), 500):
                                supabase.table("ledger_logs").insert(records[i:i + 500]).execute()
                                
                            st.success(f"✅ Successfully imported {len(records)} records!")
                            st.rerun()
            except Exception as e:
                st.error(f"❌ Error reading file: {e}")