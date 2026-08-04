# Third-Party Integrations

## 1. Supabase (Authentication)
- **Purpose:** Handles all user authentication (login, password resets).
- **How it works:** The frontend uses the Supabase JS client to authenticate and receive a JWT. The backend uses the JWT to identify the user, then checks the internal `user_profiles` Postgres table to determine their RBAC (Role-Based Access Control) permissions.
- **Quirks:** You cannot arbitrarily query Supabase users from the backend without the `SUPABASE_SERVICE_ROLE_KEY`.

## 2. Metabase (UrbanPiper POS Data)
- **Purpose:** Source of truth for Dish Sales.
- **How it works:** Instead of querying the massive production ClickHouse database directly, the pipeline hits the Curefoods Metabase API to execute pre-defined queries.
- **Quirks:** Rate limits and timeout risks if querying too large a date range. Relies on the underlying Metabase card not changing its schema.

## 3. SupplyNote (Ingredient Consumption)
- **Purpose:** Source of truth for Kitchen Consumption.
- **How it works:** Playwright headless browser script logs into the UI and downloads CSVs.
- **Quirks/Fragility:** Extreme fragility. There is no API. If SupplyNote adds a CAPTCHA, enforces 2FA, or redesigns their dashboard buttons, the pipeline will completely break and require script updates.
