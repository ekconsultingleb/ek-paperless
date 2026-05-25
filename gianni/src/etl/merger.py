import pandas as pd
from etl.utils import make_columns_numeric


def merge(cleaned: dict) -> dict:

    disc_by_desc = cleaned.get("discount by description by employee")
    disc_by_invoice = cleaned.get("discount by invoice with details")
    disc_by_item = cleaned.get("discount by items")
    cols = ["check", "description", "qty", "discount", "amount", "discount_percentage"]

    if disc_by_desc is not None and disc_by_invoice is not None:
        disc_by_desc_100 = disc_by_desc[disc_by_desc["discount_percentage"] > 0.95].copy()
        cleaned["disc_by_desc__disc_by_invoice"] = disc_by_desc_100.merge(
            disc_by_invoice,
            how="left",
            on="check",
        )[cols]

    if disc_by_desc is not None and disc_by_item is not None:
        disc_by_item__disc_by_desc = disc_by_item.merge(
            disc_by_desc,
            how="left",
            on="check",
        )[cols]
        disc_by_item__disc_by_desc = disc_by_item__disc_by_desc[
            disc_by_item__disc_by_desc["discount_percentage"] > 0.95
        ].copy()

        if disc_by_item__disc_by_desc.notna().any().any():

            ids = disc_by_item__disc_by_desc.index
            cleaned["disc_by_item__disc_by_desc"] = make_columns_numeric(
                disc_by_item__disc_by_desc,
                ["qty", "discount", "amount", "discount_percentage"],
            )
            cleaned["discount by items"] = cleaned["discount by items"].drop(index=ids)

    ib_parts: list[tuple[str, pd.DataFrame]] = []
    for name, df in cleaned.items():
        if isinstance(df, pd.DataFrame) and name.startswith("requisition summary IB "):
            ib_parts.append((name, df))

    if ib_parts:
        try:
            ib_parts_sorted = sorted(
                ib_parts,
                key=lambda x: int(x[0].split("requisition summary IB ")[1]),
            )
        except (IndexError, ValueError):
            ib_parts_sorted = ib_parts

        frames = [df for _, df in ib_parts_sorted]
        if frames:
            cleaned["requisition summary IB"] = pd.concat(frames, ignore_index=True)

    return cleaned