import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def main():
    load_dotenv()
    pg_url = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"
    engine = create_engine(pg_url)

    print("1. Loading Recipe Master CSV...")
    csv_path = r'd:\demand-planning\reference data\Recipe master.csv'
    headers = [
        'Sno.', 'SN _id', 'Recipe_Id', 'Recipe_Code', 'Item_Name', 'Packaged',
        'Veg', 'Menu Item', 'Ingredient', 'Code', 'Base_Unit', 'Batch_Size',
        'Ingredient Quantity', 'Outlets Mapped', 'Unit_Value', 'Unit',
        'Base_Unit_Value', 'isCritical', 'Type'
    ]
    
    # 1. Read the raw rows, ignoring the existing shifted header
    df = pd.read_csv(csv_path, header=None, skiprows=1, on_bad_lines='skip', low_memory=False)
    
    # 2. Drop the 20th field (the empty trailing one)
    if df.shape[1] > 19:
        df = df.iloc[:, :19]
        
    # 3. Re-map the correct header
    df.columns = headers
    
    # Clean and rename columns for Postgres
    # Now that headers are correctly aligned, Dish Name is in 'Item_Name' and SKU is in 'Code'
    df = df[['Item_Name', 'Code', 'Ingredient Quantity', 'Unit']].copy()
    df = df.dropna(subset=['Item_Name', 'Code'])
    df.columns = ['dish_name', 'ingredient', 'qty_per_unit', 'unit']
    
    # Ensure quantity is numeric
    df['qty_per_unit'] = pd.to_numeric(df['qty_per_unit'], errors='coerce').fillna(0)

    print(f"2. Inserting {len(df)} rows into 'recipe_master' table...")
    df.to_sql('recipe_master', engine, if_exists='replace', index=False)

    print("3. Creating 'item_alias_mapping' table...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS item_alias_mapping (
                id SERIAL PRIMARY KEY,
                pos_name TEXT NOT NULL,
                pos_option TEXT,
                recipe_name TEXT NOT NULL,
                multiplier FLOAT DEFAULT 1.0,
                is_manual_mapping BOOLEAN DEFAULT FALSE,
                confidence TEXT DEFAULT 'high',
                UNIQUE(pos_name, pos_option, recipe_name)
            );
        """))
        
        print("4. Auto-seeding exact matches from local CSV...")
        order_items_csv = r'd:\demand-planning\reference data\Order Items.csv'
        if os.path.exists(order_items_csv):
            oi_df = pd.read_csv(order_items_csv, usecols=['Item Name'], on_bad_lines='skip', low_memory=False)
            unique_items = oi_df['Item Name'].dropna().unique()
            
            # Find exact matches with recipe master
            recipe_names = set(df['dish_name'].unique())
            exact_matches = [name for name in unique_items if name in recipe_names]
            
            for match in exact_matches:
                conn.execute(text(f"""
                    INSERT INTO item_alias_mapping (pos_name, pos_option, recipe_name, multiplier, is_manual_mapping, confidence)
                    VALUES ('{match.replace("'", "''")}', NULL, '{match.replace("'", "''")}', 1.0, FALSE, 'high')
                    ON CONFLICT (pos_name, pos_option, recipe_name) DO NOTHING;
                """))
        
        print("5. Seeding top 5 revenue-driving manual aliases (MVP)...")
        manual_seeds = [
            ("Chocolate Truffle Eggless Cake", "500 gms (Serves 4-6)", "Eggless Chocolate Truffle Cake [500g]", 1.0),
            ("Chocolate Truffle Cake", "1/2 Kg", "Chocolate Truffle Cake (1/2 kg)", 1.0),
            ("Butterscotch Eggless Cake", "500 gms (Serves 4-6)", "Eggless Butterscotch Delight Cake [1kg]", 0.5),
            ("Mango Fruit Mini Cake - 300 Gms", None, "Mango Fruit Pop", 1.0),
            ("Special Masala Chicken Biryani (Bachelor)", None, "Aligarh House - Special Masala Chicken Biryani (475 gm)-SFE", 1.0)
        ]
        
        for pos_name, pos_option, recipe, mult in manual_seeds:
            opt_val = f"'{pos_option}'" if pos_option else "NULL"
            conn.execute(text(f"""
                INSERT INTO item_alias_mapping (pos_name, pos_option, recipe_name, multiplier, is_manual_mapping, confidence)
                VALUES ('{pos_name}', {opt_val}, '{recipe}', {mult}, TRUE, 'low')
                ON CONFLICT (pos_name, pos_option, recipe_name) DO NOTHING;
            """))
            
        conn.commit()

    print("Success! Recipe master loaded and alias table initialized.")

if __name__ == "__main__":
    main()
