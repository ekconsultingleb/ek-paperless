import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from fpdf import FPDF
import json
from modules.nav_helper import build_outlet_location_sidebar, get_all_clients, get_outlets_for_client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- PDF GENERATOR HELPER FUNCTION ---
def generate_inventory_pdf(df, report_date, client, outlet, location, user_name, missing_items=None):
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Official Inventory Count Report", ln=True, align="C")

    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {report_date}", ln=True)
    pdf.cell(0, 6, f"Branch: {client} | Outlet: {outlet} | Location: {location}", ln=True)
    pdf.cell(0, 6, f"Generated: {datetime.now(zoneinfo.ZoneInfo('Asia/Beirut')).strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(80, 8, "Item Name", border=1, fill=True)
    pdf.cell(50, 8, "Category", border=1, fill=True)
    pdf.cell(30, 8, "Quantity", border=1, align="C", fill=True)
    pdf.cell(30, 8, "Unit", border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("helvetica", "", 9)
    for _, row in df.iterrows():
        item = str(row.get('item_name', ''))[:40]
        cat = str(row.get('category', ''))[:25]
        qty = str(row.get('quantity', '0'))
        unit = str(row.get('count_unit', 'pcs'))[:10]
        pdf.cell(80, 8, item, border=1)
        pdf.cell(50, 8, cat, border=1)
        pdf.cell(30, 8, qty, border=1, align="C")
        pdf.cell(30, 8, unit, border=1, align="C")
        pdf.ln()

    # Missing items section
    if missing_items:
        pdf.ln(8)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_fill_color(255, 220, 180)
        pdf.cell(0, 8, "Additional Items (Action Required)", ln=True, fill=True)
        pdf.set_font("helvetica", "", 9)
        for item in missing_items:
            if isinstance(item, dict):
                pdf.cell(0, 7, f"  - {item['name']}  x  {item['qty']}", ln=True)
            else:
                pdf.cell(0, 7, f"  - {item}", ln=True)
        pdf.set_font("helvetica", "I", 8)
        pdf.cell(0, 6, "Please add these items to the master list via the Control Panel.", ln=True)

    return bytes(pdf.output())

# --- THE CUMULATIVE COUNTING LOGIC ---
def add_inventory_qty(item_key, row_dict, input_key):
    added_val = st.session_state.get(input_key, 0.0)
    if added_val > 0:
        if item_key not in st.session_state['mobile_counts']:
            st.session_state['mobile_counts'][item_key] = {'row_data': row_dict, 'qty': 0.0}
        st.session_state['mobile_counts'][item_key]['qty'] += added_val
        st.session_state[input_key] = 0.0
        # Mark draft as dirty — actual save is debounced (max 1 API call per 30s)
        st.session_state['_draft_dirty'] = True

def undo_inventory_count(item_key):
    if item_key in st.session_state['mobile_counts']:
        del st.session_state['mobile_counts'][item_key]
        # Mark draft as dirty — debounced save handles the actual API call
        st.session_state['_draft_dirty'] = True

# ── DRAFT AUTO-SAVE / RESTORE ─────────────────────────────────────────────
# SCALE NOTE: We never save on every keystroke — that would destroy Supabase
# under load (100+ restaurants × 200 items = 20,000+ API calls per session).
# Instead we use a dirty flag + 30-second debounce:
#   - Every item add/undo sets _draft_dirty = True  (zero API calls)
#   - Once per 30 seconds, if dirty, we do ONE upsert  (1 API call)
#   - On submit/discard we do ONE delete  (1 API call)
# Result: ~5-10 API calls per full count session regardless of item count.

DRAFT_SAVE_INTERVAL_SECONDS = 30

def save_draft(supabase, user, client, outlet, location, counts):
    """Upsert current cart to inventory_drafts. Call only from debounce check."""
    try:
        if not counts:
            supabase.table("inventory_drafts")                .delete()                .eq("user_name", user)                .eq("client_name", client)                .eq("outlet", outlet)                .execute()
            return
        draft = {
            "user_name":   user,
            "client_name": client,
            "outlet":      outlet,
            "location":    location,
            "draft_data":  json.dumps(counts),
            "updated_at":  datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).isoformat()
        }
        supabase.table("inventory_drafts")            .upsert(draft, on_conflict="user_name,client_name,outlet")            .execute()
        st.session_state['_draft_dirty'] = False
        st.session_state['_draft_last_saved'] = datetime.now().timestamp()
    except Exception:
        pass  # Draft save is best-effort — never block the user

def maybe_save_draft(supabase, user, client, outlet, location, counts):
    """Debounced save — hits Supabase immediately on first item, then every 30s.
    This ensures even a quick refresh captures all counted items."""
    if not st.session_state.get('_draft_dirty', False):
        return  # Nothing changed since last save
    last_saved = st.session_state.get('_draft_last_saved', 0)
    is_first_save = (last_saved == 0)  # Never saved before in this session
    seconds_since = datetime.now().timestamp() - last_saved
    if is_first_save or seconds_since >= DRAFT_SAVE_INTERVAL_SECONDS:
        save_draft(supabase, user, client, outlet, location, counts)

def load_draft(supabase, user, client, outlet):
    """Return saved draft counts dict or None.
    Ensures row_data values are properly typed after JSON round-trip."""
    try:
        res = supabase.table("inventory_drafts")            .select("draft_data, updated_at")            .eq("user_name", user)            .eq("client_name", client)            .eq("outlet", outlet)            .execute()
        if res.data:
            row = res.data[0]
            raw = json.loads(row["draft_data"])
            # Normalize after JSON round-trip: ensure qty is float
            # and row_data keys/values are clean strings
            counts = {}
            for item_key, item_val in raw.items():
                # Keep item_key exactly as saved — must match df_items item_name
                clean_key = str(item_key)
                row_data  = {str(k): v for k, v in item_val.get('row_data', {}).items()}
                # Ensure item_name inside row_data matches the key
                if 'item_name' in row_data:
                    clean_key = str(row_data['item_name'])
                counts[clean_key] = {
                    'qty':      float(item_val.get('qty', 0)),
                    'row_data': row_data
                }
            updated = str(row.get("updated_at", ""))[:16].replace("T", " ")
            return counts, updated
    except Exception:
        pass
    return None, None

def delete_draft(supabase, user, client, outlet):
    """Delete draft after successful submission."""
    try:
        supabase.table("inventory_drafts")            .delete()            .eq("user_name", user)            .eq("client_name", client)            .eq("outlet", outlet)            .execute()
    except Exception:
        pass

# ==========================================
# MAIN RENDER FUNCTION
# ==========================================
def render_inventory(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📋 Inventory Count")
    supabase = get_supabase()

    # --- 🔒 INITIALIZE SESSION STATES FOR LOCKS & CARTS ---
    if 'mobile_counts' not in st.session_state:
        st.session_state['mobile_counts'] = {}
    if 'missing_items' not in st.session_state:
        st.session_state['missing_items'] = []
        
    if 'submit_lock' not in st.session_state:
        st.session_state['submit_lock'] = False
    if '_draft_dirty' not in st.session_state:
        st.session_state['_draft_dirty'] = False
    if '_draft_last_saved' not in st.session_state:
        st.session_state['_draft_last_saved'] = 0.0
    if 'draft_checked' not in st.session_state:
        st.session_state['draft_checked'] = False
    if '_pending_draft' not in st.session_state:
        st.session_state['_pending_draft'] = {}
    if '_pending_draft_time' not in st.session_state:
        st.session_state['_pending_draft_time'] = ''

    def lock_submit():
        st.session_state['submit_lock'] = True

    # ── Sidebar navigation (shared helper) ───────────────────────────────────
    final_client, final_outlet, final_location_sidebar = build_outlet_location_sidebar(
        assigned_client, assigned_outlet, assigned_location,
        outlet_key="inv_outlet", location_key="inv_location"
    )


    # ---------------------------------------------------------
    # SUB-VIEW A: THE REPORTS & CONSOLIDATED TOTALS (CHEF VIEW)
    # ---------------------------------------------------------
    def show_reports():
        st.info("👁️ Viewing Inventory Logs & Totals")

        _is_admin_rep = role.lower() in ["admin", "admin_all"]
        if _is_admin_rep:
            _rep_col1, _rep_col2 = st.columns(2)
            with _rep_col1:
                _all_clients = ["All"] + get_all_clients()
                rep_client = st.selectbox("🏢 Client", _all_clients, key="inv_rep_client")
            with _rep_col2:
                _rep_outlets = ["All"] + (get_outlets_for_client(rep_client) if rep_client != "All" else [])
                rep_outlet = st.selectbox("🏪 Outlet", _rep_outlets, key="inv_rep_outlet")
        else:
            rep_client = final_client
            rep_outlet = final_outlet

        today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
        default_start = today - timedelta(days=7)

        date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today, key="report_dates")

        if len(date_range) == 2:
            start_date, end_date = date_range

            query = supabase.table("inventory_logs").select("*").gte("date", str(start_date)).lte("date", str(end_date))

            if rep_client and rep_client not in ["Select Branch", "All"]:
                query = query.ilike("client_name", f"%{rep_client}%")
            if rep_outlet and rep_outlet != "None":
                query = query.ilike("outlet", f"%{rep_outlet}%")
                
            archive_res = query.order("date", desc=True).limit(5000).execute()
            df_archive = pd.DataFrame(archive_res.data)
            df_archive = df_archive.drop(columns=[c for c in ["id", "created_at"] if c in df_archive.columns])

            if not df_archive.empty:
                tab_raw, tab_total = st.tabs(["📜 Raw Logs (By User)", "📊 Consolidated Totals"]) 
                with tab_raw:
                    st.write("### Individual Staff Counts")
                    pdf_bytes = generate_inventory_pdf(
                        df_archive, f"{start_date} to {end_date}",
                        rep_client, rep_outlet, "Multiple Locations", "System Report"
                    )
                    st.download_button(
                        label="🖨️ Download Raw PDF Report",
                        data=pdf_bytes,
                        file_name=f"Inventory_Report_{start_date}_to_{end_date}.pdf",
                        mime="application/pdf",
                        type="primary",
                        key="raw_pdf_btn"
                    )

                    can_edit = role.lower() in ["manager", "admin", "admin_all"]

                    if can_edit:
                        st.caption("✏️ You can correct quantities below. Only the **Quantity** column is editable.")

                        # Determine which columns to lock (everything except quantity)
                        lock_cols = [c for c in df_archive.columns if c != "quantity"]

                        edited_raw = st.data_editor(
                            df_archive,
                            width="stretch",
                            hide_index=True,
                            disabled=lock_cols,
                            column_config={
                                "quantity": st.column_config.NumberColumn("Quantity", min_value=0.0, step=0.5),
                            },
                            key="raw_log_editor"
                        )

                        if st.button("💾 Save Corrections", type="primary", width="stretch", key="save_raw_edits"):
                            orig = df_archive.copy()
                            orig["quantity"] = pd.to_numeric(orig["quantity"], errors="coerce")
                            edited_raw["quantity"] = pd.to_numeric(edited_raw["quantity"], errors="coerce")

                            changed = edited_raw[edited_raw["quantity"] != orig["quantity"]]
                            if changed.empty:
                                st.info("No changes detected.")
                            else:
                                try:
                                    for _, row in changed.iterrows():
                                        supabase.table("inventory_logs").update(
                                            {"quantity": float(row["quantity"])}
                                        ).eq("id", row["id"]).execute()
                                    st.success(f"✅ {len(changed)} record(s) updated.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Failed to save: {e}")
                    else:
                        st.dataframe(df_archive, width="stretch", hide_index=True)
                    
                with tab_total:
                    st.write("### Total Inventory by Item")
                    st.info("💡 This view merges counts from all staff and locations into one final total per item.")
                    
                    df_math = df_archive.copy()
                    df_math['quantity'] = pd.to_numeric(df_math['quantity'], errors='coerce').fillna(0)
                    
                    df_totals = df_math.groupby(
                        ['category', 'sub_category', 'item_name', 'count_unit'], 
                        dropna=False
                    )['quantity'].sum().reset_index()
                    
                    df_totals = df_totals.sort_values(by=['category', 'item_name'])
                    st.dataframe(df_totals, width="stretch", hide_index=True)
                    
                    csv_totals = df_totals.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="💾 Download Consolidated Totals (CSV)",
                        data=csv_totals,
                        file_name=f"Consolidated_Inventory_{start_date}_to_{end_date}.csv",
                        mime="text/csv",
                        type="primary",
                        key="totals_csv_btn"
                    )
            else:
                st.warning(f"No logs found for this branch between {start_date} and {end_date}.")
        else:
            st.info("Please select both a Start Date and an End Date.")

    # ---------------------------------------------------------
    # SUB-VIEW B: THE COUNTING INTERFACE (STAFF VIEW)
    # ---------------------------------------------------------
    def show_counting():
        if 'last_inv_receipt' in st.session_state:
            st.success("✅ **Success!** Your count was safely stored in the cloud.")
            st.download_button(
                label="🖨️ Download Proof of Count (PDF Receipt)",
                data=st.session_state['last_inv_receipt']['bytes'],
                file_name=st.session_state['last_inv_receipt']['filename'],
                mime="application/pdf",
                type="primary",
                key="receipt_btn"
            )
            if st.button("Start New Count", width="stretch", key="new_count_btn"):
                del st.session_state['last_inv_receipt']
                st.session_state['submit_lock'] = False
                delete_draft(supabase, user, final_client, final_outlet)
                st.rerun()
            st.divider()
            return

        # ── DRAFT RESTORE PROMPT ──────────────────────────────────────────
        # Only check DB for a draft if cart is empty and we haven't checked yet
        if not st.session_state['mobile_counts'] and not st.session_state.get('draft_checked'):
            saved_counts, saved_time = load_draft(supabase, user, final_client, final_outlet)
            st.session_state['draft_checked'] = True  # Mark checked regardless
            if saved_counts:
                # Store in a separate key so it survives until user decides
                st.session_state['_pending_draft'] = saved_counts
                st.session_state['_pending_draft_time'] = saved_time

        # Show banner if there's a pending draft waiting for decision
        if st.session_state.get('_pending_draft') and not st.session_state['mobile_counts']:
            saved_counts = st.session_state['_pending_draft']
            saved_time   = st.session_state.get('_pending_draft_time', '')
            st.warning(f"📋 **Unsaved count found** from {saved_time} — {len(saved_counts)} item(s) were counted.")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                if st.button("✅ Resume Previous Count", type="primary", width="stretch", key="resume_draft"):
                    st.session_state['mobile_counts'] = saved_counts
                    st.session_state['_pending_draft'] = {}
                    st.session_state['_draft_dirty'] = False
                    st.rerun()
            with col_r2:
                if st.button("🗑️ Discard & Start Fresh", width="stretch", key="discard_draft"):
                    delete_draft(supabase, user, final_client, final_outlet)
                    st.session_state['_pending_draft'] = {}
                    st.rerun()
            st.divider()

        # MEGA-FETCH LOOP
        all_items = []
        page_size, start_row = 1000, 0
        
        if final_outlet and str(final_outlet).strip() != "" and final_outlet != "None":
            while True:
                query = supabase.table("master_items").select("*")
                if final_client and final_client not in ["All", "Select Branch", "All Branches"]:
                    query = query.ilike("client_name", f"%{final_client}%")
                query = query.ilike("outlet", f"%{final_outlet}%")
                res = query.range(start_row, start_row + page_size - 1).execute()
                
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_items = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'item_type'])
            st.warning(f"⚠️ No items found for {final_outlet}.")
        else:
            df_items = pd.DataFrame(all_items)
            df_items.columns = [str(c).strip().lower() for c in df_items.columns]
            if 'location' not in df_items.columns: df_items['location'] = "Main Store"
            if 'item_type' in df_items.columns: df_items = df_items[df_items['item_type'].astype(str).str.lower() == 'inventory']

        # Location already selected via build_outlet_location_sidebar
        loc_filter = final_location_sidebar

        if not df_items.empty:
            if loc_filter and loc_filter.lower() not in ['all', 'none', '']:
                df_items = df_items[df_items['location'].str.strip().str.title() == loc_filter]
            df_items = df_items.drop_duplicates(subset=['item_name']).copy()
            if df_items.empty:
                st.warning(f"⚠️ No items found for location **{loc_filter}**. This location may not have items uploaded yet.")

        # Store context for auto-save callbacks
        st.session_state['_inv_draft_ctx'] = {
            'user': user, 'client': final_client,
            'outlet': final_outlet, 'location': loc_filter
        }

        # ── DEBOUNCED DRAFT SAVE ──────────────────────────────────────────
        # Runs on every Streamlit rerun but only hits Supabase every 30s max.
        # This is the ONLY place we write to Supabase during counting.
        if st.session_state['mobile_counts']:
            maybe_save_draft(
                supabase, user, final_client, final_outlet,
                loc_filter, st.session_state['mobile_counts']
            )

        count_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")), key="count_date")
        st.divider()

        with st.expander("➕ Found an item not on the list?"):
            col_flag, col_qty, col_btn = st.columns([3, 1, 1], vertical_alignment="bottom")
            with col_flag:
                flag_name = st.text_input("Item Name", placeholder="e.g. Redbull 355ml", key="flag_item_name", label_visibility="collapsed")
            with col_qty:
                flag_qty = st.number_input("Qty", min_value=0.0, step=1.0, format="%g", key="flag_item_qty", label_visibility="collapsed")
            with col_btn:
                if st.button("Add", width="stretch", key="flag_item_btn"):
                    name = flag_name.strip()
                    existing_names = [x['name'] for x in st.session_state['missing_items']]
                    if name and name not in existing_names:
                        st.session_state['missing_items'].append({"name": name, "qty": flag_qty})
                        st.rerun()

            if st.session_state['missing_items']:
                for i, m in enumerate(st.session_state['missing_items']):
                    col_m, col_x = st.columns([5, 1])
                    col_m.markdown(f"• **{m['name']}** — {m['qty']}")
                    if col_x.button("✕", key=f"remove_flag_{i}"):
                        st.session_state['missing_items'].pop(i)
                        st.rerun()

        st.subheader("🔍 Filter & Count")
        search_query = st.text_input("🔍 Quick Search", placeholder="Find items...", key="search_bar")
        
        c1, c2 = st.columns(2)
        with c1:
            cats = sorted(list(df_items['category'].dropna().astype(str).unique())) if not df_items.empty else []
            cat_options = ["All"] + cats
            # Default to "All" if items were resumed so all counted items are visible
            has_resumed = bool(st.session_state.get('mobile_counts'))
            cat_default = 0 if has_resumed else (1 if cats else 0)
            selected_category = st.selectbox("📂 Category", cat_options, index=cat_default, key="cat_filter")
        with c2:
            df_grp_list = df_items if selected_category == "All" else df_items[df_items['category'] == selected_category]
            grps = sorted(list(df_grp_list['sub_category'].dropna().astype(str).unique())) if not df_grp_list.empty else []
            grp_options = ["All"] + grps
            grp_default = 0 if has_resumed else (1 if grps else 0)
            selected_group = st.selectbox("🏷️ Sub Category", grp_options, index=grp_default, key="sub_filter")

        if not df_items.empty:
            df_display = df_items.copy()
            if search_query:
                # Search overrides category/sub-category — find the item anywhere
                df_display = df_display[df_display['item_name'].str.contains(search_query, case=False, na=False)]
            else:
                if selected_category != "All":
                    df_display = df_display[df_display['category'] == selected_category]
                if selected_group != "All":
                    df_display = df_display[df_display['sub_category'] == selected_group]
        else:
            df_display = pd.DataFrame()

        total_items = len(df_display)
        counted_in_view = sum(1 for item in df_display['item_name'] if item in st.session_state['mobile_counts']) if not df_display.empty else 0
        
        st.markdown(f"""
            <div style='display: flex; justify-content: space-between; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
                <span style='color: #00ff00;'>✅ {counted_in_view} Counted</span>
                <span style='color: white;'>📝 {total_items} Items in {selected_group}</span>
            </div>
        """, unsafe_allow_html=True)

        if df_display.empty:
            st.info("No items found.")
        else:
            for index, row in df_display.iterrows():
                item_name = row['item_name']
                cart_data = st.session_state['mobile_counts'].get(item_name)
                current_total = cart_data['qty'] if cart_data else 0.0
                
                with st.container(border=True):
                    if current_total > 0:
                        st.markdown(f"🟢 **{item_name}** &nbsp;|&nbsp; ✅ Total: **{current_total}** {row.get('count_unit', 'pcs')}")
                    else:
                        st.markdown(f"🔴 **{item_name}** &nbsp;|&nbsp; 📦 {row.get('count_unit', 'pcs')}")
                    
                    col_add, col_btn = st.columns([3, 1], vertical_alignment="center")
                    input_key = f"inv_add_{row.get('id', index)}_{item_name}"
                    
                    with col_add:
                        # No value= param — session_state is the only source of truth
                        # This prevents the "widget created with default value AND session state" warning
                        if input_key not in st.session_state:
                            st.session_state[input_key] = 0.0
                        st.number_input(
                            "+ Add Qty",
                            min_value=0.0, step=1.0, format="%g",
                            key=input_key,
                            on_change=add_inventory_qty,
                            args=(item_name, row.to_dict(), input_key),
                            label_visibility="collapsed",
                            placeholder="Type amount and press Enter"
                        )
                    with col_btn:
                        if current_total > 0:
                            if st.button("🗑️ Undo", key=f"undo_{row.get('id', index)}_{item_name}"):
                                undo_inventory_count(item_name)
                                st.rerun()

        st.divider()
        cart_size = len(st.session_state['mobile_counts'])
        if cart_size > 0:
            st.success(f"🛒 **{cart_size} items** ready to submit.")
            with st.expander("👀 Review & Submit Count", expanded=True):
                preview_list = [{"Item": v['row_data'].get('item_name', k), "Total Counted": v['qty'], "Unit": v['row_data'].get('count_unit', '')} for k, v in st.session_state['mobile_counts'].items()]
                st.dataframe(pd.DataFrame(preview_list), width="stretch", hide_index=True)

                if st.session_state['missing_items']:
                    _mi_summary = ', '.join(f"{x['name']} ({x['qty']})" for x in st.session_state['missing_items'])
                    st.warning(f"⚠️ **{len(st.session_state['missing_items'])} item(s) added manually** — will appear on the PDF report: {_mi_summary}")

                if st.button("🚀 SUBMIT ALL COUNTS TO CLOUD", type="primary", width="stretch", key="submit_cloud_btn", on_click=lock_submit, disabled=st.session_state['submit_lock']):
                    with st.spinner("Saving to database... Please wait! Do not refresh."):
                        logs = []
                        for i_name, data in st.session_state['mobile_counts'].items():
                            r_data = data['row_data']
                            logs.append({
                                "date": str(count_date),
                                "client_name": final_client,
                                "outlet": final_outlet,
                                "location": loc_filter,
                                "counted_by": user,
                                "item_name": r_data.get('item_name', i_name),
                                "product_code": str(r_data.get('product_code', '')),
                                "item_type": r_data.get('item_type', ''),
                                "category": r_data.get('category', ''),
                                "sub_category": r_data.get('sub_category', ''),
                                "quantity": float(data['qty']),
                                "count_unit": r_data.get('count_unit', 'pcs')
                            })

                        if logs:
                            try:
                                supabase.table("inventory_logs").insert(logs).execute()
                                df_receipt = pd.DataFrame(logs)
                                pdf_bytes = generate_inventory_pdf(
                                    df_receipt, str(count_date), final_client, final_outlet,
                                    loc_filter, user, missing_items=st.session_state['missing_items']
                                )
                                st.session_state['last_inv_receipt'] = {"bytes": pdf_bytes, "filename": f"Inventory_Receipt_{final_outlet.replace(' ', '_')}_{str(count_date)}.pdf"}

                                st.session_state['mobile_counts'] = {}
                                st.session_state['missing_items'] = []
                                st.session_state['submit_lock'] = False
                                st.session_state['draft_checked'] = False
                                delete_draft(supabase, user, final_client, final_outlet)
                                st.rerun()

                            except Exception as e:
                                st.session_state['submit_lock'] = False
                                st.error(f"❌ Database Error: {e}")

    # ---------------------------------------------------------
    # TRAFFIC COP: DECIDE WHAT TO SHOW BASED ON ROLE
    # ---------------------------------------------------------
    try:
        user_role = role.lower()
        
        if user_role == "viewer":
            show_reports()
            
        elif user_role in ["staff", "chef", "bar manager", "manager", "admin", "admin_all"]:
            tab_c, tab_r = st.tabs(["✍️ Count Inventory", "📊 View Reports & Totals"])
            with tab_c:
                show_counting()
            with tab_r:
                show_reports()
                
        else:
            st.warning("⚠️ Unrecognized user role. Please contact your administrator.")
            
    except Exception as e:
        st.error(f"❌ System Error: {e}")
