def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool,
):
    _init_form()

    # Absorb sub-recipe result from dialog
    result = st.session_state.get("sub_recipe_result")
    if result is not None:
        idx = result["parent_index"]
        if 0 <= idx < len(st.session_state["form_lines"]):
            st.session_state["form_lines"][idx]["sub_data"] = {
                "batch_qty":  result["batch_qty"],
                "batch_unit": result["batch_unit"],
                "lines":      result["lines"],
            }
        st.session_state["sub_recipe_result"] = None

    # Photo dialog
    if st.session_state.get("form_show_photo"):
        _photo_dialog(
            supabase,
            st.session_state["form_saved_id"],
            st.session_state["form_saved_name"],
        )

    # Success screen
    if st.session_state.get("form_photo_done"):
        st.success(
            f"**{st.session_state.get('form_saved_name','')}** saved!"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("New recipe", use_container_width=True):
                _reset_form()
                st.rerun()
        with c2:
            if st.button(
                "Go to library", type="primary",
                use_container_width=True
            ):
                _reset_form()
                st.session_state["recipe_tab"] = "library"
                st.rerun()
        return

    # Open sub-recipe dialog if triggered
    if st.session_state.get("open_sub_idx") is not None:
        idx = st.session_state.pop("open_sub_idx")
        _sub_recipe_dialog(idx)

    # ── RECIPE NAME ───────────────────────────────────────────────────────
    st.text_input(
        "Recipe name",
        placeholder="Type here the recipe name",
        key="form_recipe_name",
        label_visibility="collapsed",
    )

    # ── CATEGORY ─────────────────────────────────────────────────────────
    st.radio(
        "Category",
        ["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
        horizontal=True,
        key="form_category",
        label_visibility="collapsed",
    )

    # ── PORTIONS + UNIT side by side ──────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.number_input(
            "Portions", min_value=1, value=1,
            key="form_portions",
        )
    with c2:
        st.selectbox(
            "Unit",
            ["Plate", "Portion", "Kg", "Litre", "Batch"],
            key="form_yield_unit",
        )

    st.markdown("---")

    # ── SINGLE INGREDIENT ENTRY ROW ───────────────────────────────────────
    # Initialise transient input state
    if "ing_input_name" not in st.session_state:
        st.session_state["ing_input_name"]    = ""
    if "ing_input_qty" not in st.session_state:
        st.session_state["ing_input_qty"]     = 0.0
    if "ing_input_unit" not in st.session_state:
        st.session_state["ing_input_unit"]    = "g"
    if "ing_input_prod" not in st.session_state:
        st.session_state["ing_input_prod"]    = False

    c1, c2, c3, c4, c5 = st.columns([3, 1.2, 1.2, 1.2, 1])
    with c1:
        ing_name = st.text_input(
            "Ingredient",
            value=st.session_state["ing_input_name"],
            placeholder="Ingredient",
            key="ing_name_input",
            label_visibility="collapsed",
        )
    with c2:
        ing_qty = st.number_input(
            "Qty",
            min_value=0.0, step=1.0,
            value=st.session_state["ing_input_qty"],
            key="ing_qty_input",
            label_visibility="collapsed",
            format="%.0f",
        )
    with c3:
        ing_unit = st.selectbox(
            "Unit",
            UNITS,
            index=UNITS.index(st.session_state["ing_input_unit"])
                  if st.session_state["ing_input_unit"] in UNITS else 0,
            key="ing_unit_input",
            label_visibility="collapsed",
        )
    with c4:
        ing_prod = st.radio(
            "Type",
            ["Buy", "Prod"],
            horizontal=True,
            key="ing_prod_input",
            label_visibility="collapsed",
        )
        is_production = ing_prod == "Prod"
    with c5:
        add_clicked = st.button(
            "Add",
            use_container_width=True,
            type="primary",
            key="ing_add_btn",
        )

    if add_clicked:
        if ing_name.strip():
            if is_production:
                # Save the input first then open sub-recipe dialog
                new_idx = len(st.session_state["form_lines"])
                st.session_state["form_lines"].append({
                    "chef_input":    ing_name.strip(),
                    "qty":           ing_qty,
                    "unit":          ing_unit,
                    "is_production": True,
                    "sub_data":      None,
                })
                # Clear inputs
                st.session_state.pop("ing_name_input",  None)
                st.session_state.pop("ing_qty_input",   None)
                st.session_state.pop("ing_unit_input",  None)
                st.session_state.pop("ing_prod_input",  None)
                st.session_state["ing_input_name"] = ""
                st.session_state["ing_input_qty"]  = 0.0
                st.session_state["ing_input_unit"] = "g"
                st.session_state["ing_input_prod"] = False
                # Open sub-recipe dialog for this new line
                st.session_state["open_sub_idx"] = new_idx
                st.rerun()
            else:
                st.session_state["form_lines"].append({
                    "chef_input":    ing_name.strip(),
                    "qty":           ing_qty,
                    "unit":          ing_unit,
                    "is_production": False,
                    "sub_data":      None,
                })
                # Clear inputs so row resets
                st.session_state.pop("ing_name_input",  None)
                st.session_state.pop("ing_qty_input",   None)
                st.session_state.pop("ing_unit_input",  None)
                st.session_state.pop("ing_prod_input",  None)
                st.session_state["ing_input_name"] = ""
                st.session_state["ing_input_qty"]  = 0.0
                st.session_state["ing_input_unit"] = "g"
                st.session_state["ing_input_prod"] = False
                st.rerun()
        else:
            st.caption("Enter an ingredient name first.")

    # ── ADDED INGREDIENTS LIST ────────────────────────────────────────────
    lines = st.session_state["form_lines"]
    if lines:
        st.markdown("---")
        for idx, line in enumerate(lines):
            c1, c2, c3, c4 = st.columns([4, 1, 1, 0.4])
            with c1:
                badge = "🏭" if line["is_production"] else "🛒"
                st.write(f"{badge} {line['chef_input']}")
                if line["is_production"] and line.get("sub_data"):
                    sub = line["sub_data"]
                    st.caption(
                        f"{sub['batch_qty']} {sub['batch_unit']} · "
                        f"{len(sub['lines'])} ingredient(s)"
                    )
                    if st.button(
                        "Edit sub-recipe",
                        key=f"edit_sub_{idx}",
                    ):
                        st.session_state["open_sub_idx"] = idx
                        st.rerun()
                elif line["is_production"] and line.get("sub_data") is None:
                    if st.button(
                        "Build sub-recipe",
                        key=f"build_sub_{idx}",
                    ):
                        st.session_state["open_sub_idx"] = idx
                        st.rerun()
            with c2:
                qty = st.number_input(
                    "qty",
                    min_value=0.0, step=1.0,
                    value=float(line["qty"]),
                    key=f"listed_qty_{idx}",
                    label_visibility="collapsed",
                    format="%.0f",
                )
                lines[idx]["qty"] = qty
            with c3:
                st.caption(line["unit"])
            with c4:
                if st.button("×", key=f"del_{idx}"):
                    lines.pop(idx)
                    st.session_state["form_lines"] = lines
                    st.rerun()

        st.session_state["form_lines"] = lines

    # ── METHOD ────────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Method of preparation (optional)"):
        st.text_area(
            "Method",
            placeholder=(
                "1. Marinate chicken for 2hrs\n"
                "2. Grill 4 mins each side\n"
                "3. Rest before plating"
            ),
            max_chars=500,
            height=130,
            key="form_method",
            label_visibility="collapsed",
        )
        st.caption(
            f"{len(st.session_state.get('form_method',''))} / 500"
        )

    # ── SAVE ──────────────────────────────────────────────────────────────
    st.markdown("")
    name     = st.session_state.get("form_recipe_name", "").strip()
    can_save = bool(name)

    if not name:
        st.caption("Enter a recipe name to save.")

    if st.button(
        "Save recipe",
        type="primary",
        use_container_width=True,
        disabled=not can_save,
    ):
        portions   = st.session_state.get("form_portions", 1)
        yield_unit = st.session_state.get("form_yield_unit", "Plate")
        category   = st.session_state.get("form_category", "Main")
        method     = st.session_state.get("form_method", "") or None
        ings       = [
            l for l in st.session_state["form_lines"]
            if l["chef_input"].strip()
        ]

        recipe_id = str(uuid.uuid4())
        now = datetime.now(
            zoneinfo.ZoneInfo("Asia/Beirut")
        ).isoformat()

        recipe_record = {
            "id":               recipe_id,
            "client_name":      client_name,
            "outlet":           outlet,
            "name":             name,
            "category":         category,
            "portions":         portions,
            "yield_unit":       yield_unit,
            "method":           method,
            "cost_per_portion": 0,
            "created_by":       user,
            "created_at":       now,
            "photo_url":        None,
        }

        lines_to_save = []
        for ing in ings:
            lines_to_save.append({
                "id":              str(uuid.uuid4()),
                "recipe_id":       recipe_id,
                "chef_input":      ing["chef_input"].strip(),
                "qty":             ing["qty"],
                "unit":            ing["unit"],
                "is_production":   ing["is_production"],
                "ai_resolved":     None,
                "ai_product_code": None,
                "ai_confidence":   None,
                "sub_lines":       (
                    ing["sub_data"]["lines"]
                    if ing.get("sub_data") else None
                ),
            })

        saved_id = _save_recipe(supabase, recipe_record, lines_to_save)
        if saved_id:
            st.session_state["form_saved_id"]   = saved_id
            st.session_state["form_saved_name"] = name
            st.session_state["form_show_photo"] = True
            st.rerun()