# Auth and RBAC (Role-Based Access Control)

## Authentication Flow
1. User enters email/password on the Next.js `/login` page.
2. Frontend calls Supabase JS client `signInWithEmail`.
3. Supabase verifies credentials and returns a JWT.
4. Frontend stores JWT in localStorage (`sb-token`).
5. Axios interceptor (`src/lib/api.ts`) attaches `Authorization: Bearer <token>` to all backend requests.

## Role-Based Access Control (RBAC)
Authorization is enforced **server-side** by FastAPI.

### The Role Check Process
1. FastAPI receives the JWT.
2. The `get_current_user` dependency uses the Supabase Python client to validate the token signature and get the `user.id` (UUID).
3. FastAPI queries the Postgres `user_profiles` table using the UUID to fetch the user's `role` and `is_active` status.
4. If `is_active` is false, access is denied (401).

### Defined Roles
- `super_admin`: Full access to everything, including the `/admin` user management routes.
- `admin`: Full application access, acts as a fallback for legacy endpoints.
- `planning_manager`: Can view all dashboards, reports, and forecasts.
- `demand_planner`: Day-to-day operations.
- `viewer`: Read-only access (default fallback if a role isn't found).

### Backend Enforcement
Routes are protected using the `require_role` dependency:
```python
@router.get("/sales")
def get_sales(
    user: UserContext = Depends(require_role("super_admin", "planning_manager", "demand_planner"))
):
    ...
```
