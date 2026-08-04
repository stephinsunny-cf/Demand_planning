# Frontend Route Map

The frontend is a Next.js App Router application located in `frontend/src/app`.

## Public Routes
- `/login`: Supabase email/password authentication.
- `/forgot-password`: Password recovery flow.
- `/reset-password`: Forced password reset for new invitees.

## Protected Application Routes
- `/dashboard`: High-level executive overview (KPIs, top performing brands).
- `/sales`: 
  - **Tab 1: Kitchen Consumption:** Shows raw ingredients used (SupplyNote).
  - **Tab 2: Dish Sales:** Shows finished goods sold (UrbanPiper).
- `/forecast`: Demand prediction outputs.
- `/variance`: Identifies waste/theft by comparing consumption vs. recipes.
- `/supply` & `/procurement`: Future features for generating POs (Purchase Orders).
- `/recipes`: Recipe master data management (mapping ingredients to dishes).
- `/warehouse`: Inventory tracking.
- `/alerts`: Automated system alerts (e.g., low stock, pipeline failures).
- `/reports`: Exportable static reports.

## Admin Routes
- `/admin`: Super Admin panel for inviting users and assigning RBAC roles (`planning_manager`, `demand_planner`, `viewer`).
