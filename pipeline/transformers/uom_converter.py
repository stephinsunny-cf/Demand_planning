"""
pipeline/transformers/uom_converter.py
───────────────────────────────────────
Converts all weights to grams and all volumes to ml.
Business rule: NEVER mix units in the same column.
"""

import logging
import re

import pandas as pd

log = logging.getLogger(__name__)

# ── Conversion tables ─────────────────────────────────────────────────────────

WEIGHT_TO_GRAMS: dict[str, float] = {
    "g":         1.0,
    "gm":        1.0,
    "grams":     1.0,
    "gram":      1.0,
    "kg":        1000.0,
    "kilogram":  1000.0,
    "kilograms": 1000.0,
    "mg":        0.001,
    "milligram": 0.001,
    "lb":        453.592,
    "lbs":       453.592,
    "pound":     453.592,
    "oz":        28.3495,
    "ounce":     28.3495,
}

VOLUME_TO_ML: dict[str, float] = {
    "ml":          1.0,
    "millilitre":  1.0,
    "milliliter":  1.0,
    "millilitres": 1.0,
    "milliliters": 1.0,
    "l":           1000.0,
    "litre":       1000.0,
    "liter":       1000.0,
    "litres":      1000.0,
    "liters":      1000.0,
    "dl":          100.0,
    "cl":          10.0,
    "tsp":         4.929,
    "teaspoon":    4.929,
    "tbsp":        14.787,
    "tablespoon":  14.787,
    "cup":         236.588,
    "fl oz":       29.5735,
}

# Ingredients that are always liquid (even if unit not specified)
LIQUID_INGREDIENTS = {
    "oil", "water", "milk", "cream", "sauce", "puree", "juice",
    "stock", "broth", "marinade", "vinegar", "syrup", "gravy",
}


def _normalise_unit(unit: str) -> str:
    """Lowercase, strip, remove trailing dots/spaces from unit string."""
    if not isinstance(unit, str):
        return ""
    return unit.strip().lower().rstrip(".")


def convert_qty_to_standard(qty: float, unit: str, ingredient_name: str = "") -> tuple[float, str]:
    """
    Convert a quantity+unit pair to standard (grams for solids, ml for liquids).

    Returns (converted_qty, standard_unit).
    """
    if qty is None or pd.isna(qty):
        return 0.0, "g"

    unit_clean = _normalise_unit(unit)
    qty = float(qty)

    # Check weight
    if unit_clean in WEIGHT_TO_GRAMS:
        return round(qty * WEIGHT_TO_GRAMS[unit_clean], 4), "g"

    # Check volume
    if unit_clean in VOLUME_TO_ML:
        return round(qty * VOLUME_TO_ML[unit_clean], 4), "ml"

    # Guess from ingredient name
    if ingredient_name:
        for liquid_kw in LIQUID_INGREDIENTS:
            if liquid_kw in ingredient_name.lower():
                log.debug("Guessing '%s' is liquid — treating as ml", ingredient_name)
                return qty, "ml"

    # Unknown unit — keep as-is but log warning
    if unit_clean:
        log.warning("Unknown unit '%s' for ingredient '%s' — keeping raw value", unit, ingredient_name)
    return qty, unit_clean or "g"


def convert_df_uom(df: pd.DataFrame, qty_col: str, unit_col: str,
                   ingredient_col: str = None) -> pd.DataFrame:
    """
    Apply UOM conversion to a full DataFrame in-place.
    Adds/overwrites qty_col with converted values.
    Sets unit_col to the standard unit ('g' or 'ml').
    """
    if df.empty:
        return df

    df = df.copy()
    converted_qtys = []
    converted_units = []

    for _, row in df.iterrows():
        qty = row.get(qty_col, 0)
        unit = row.get(unit_col, "")
        ingredient = row.get(ingredient_col, "") if ingredient_col else ""
        cqty, cunit = convert_qty_to_standard(qty, unit, ingredient)
        converted_qtys.append(cqty)
        converted_units.append(cunit)

    df[qty_col] = converted_qtys
    df[unit_col] = converted_units
    return df
