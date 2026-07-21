import pandas as pd
from backend.database import get_db_connection

def seed_fake_test():
    print("Seeding un-clobberable fake golden test case...")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1. Procurement Tracker
            cur.execute("DELETE FROM procurement_tracker WHERE code = 'CFTEST999'")
            cur.execute("""
                INSERT INTO procurement_tracker (code, ingredient)
                VALUES ('CFTEST999', 'Fake Test Ingredient')
            """)
            
            # 2. Recipe Master (100+1 clash)
            cur.execute("DELETE FROM recipe_master WHERE ingredient = 'CFTEST999'")
            cur.execute("""
                INSERT INTO recipe_master (dish_name, ingredient, qty_per_unit, unit)
                VALUES 
                    ('Fake Test Dish 999', 'CFTEST999', 100.0, 'g'),
                    ('Fake Test Dish 888', 'CFTEST999', 1.0, 'g')
            """)
            
            # 3. Item Alias Mapping (Map both fake dishes to the real POS item 'Palak Paneer Khichdi')
            cur.execute("DELETE FROM item_alias_mapping WHERE recipe_name LIKE 'Fake Test Dish%'")
            cur.execute("""
                INSERT INTO item_alias_mapping (pos_name, recipe_name, multiplier, confidence)
                VALUES 
                    ('Palak Paneer Khichdi', 'Fake Test Dish 999', 1.0, 'high'),
                    ('Palak Paneer Khichdi', 'Fake Test Dish 888', 1.0, 'high')
            """)
            
            # 4. Actual Usage (fact_daily_sales) for July 16
            cur.execute("DELETE FROM fact_daily_sales WHERE sku = 'CFTEST999'")
            cur.execute("""
                INSERT INTO fact_daily_sales (date, outlet, sku, brand, city, qty_sold, revenue, order_count)
                VALUES 
                    ('2026-07-16', 'Khichdi Tales Jlt', 'CFTEST999', 'Fake Brand', 'Fake City', 90.0, 0, 1)
            """)
            
        conn.commit()
    print("Seeded fake test data.")

if __name__ == '__main__':
    seed_fake_test()
