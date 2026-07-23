from backend.database import query_df

print('Query 1 (recipe_master):')
df1 = query_df("SELECT dish_name FROM recipe_master WHERE ingredient IN ('Cfimp025', 'Cfidg323')")
print(df1)

print('\nQuery 2 (recipe_master):')
df2 = query_df("""
SELECT rm.dish_name, rm.ingredient
FROM recipe_master rm
WHERE rm.ingredient IN ('Cfimp025', 'Cfidg323')
AND NOT EXISTS (
  SELECT 1 FROM item_alias_mapping am WHERE am.recipe_name = rm.dish_name
)
""")
print(df2)
