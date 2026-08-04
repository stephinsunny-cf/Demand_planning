# Project Overview: Demand Planning Engine v2

## What the App Does
The Demand Planning Engine is an internal tool built for Curefoods to forecast inventory needs, track ingredient consumption, and analyze sales trends. It bridges the gap between what is sold to customers (Dish Sales) and what ingredients are actually used in the kitchens (Kitchen Consumption).

## Who Uses It
- **Super Admins / Admins:** Full system access, user management, configuration.
- **Planning Managers:** Oversee supply chains across multiple regions/brands.
- **Demand Planners:** Day-to-day analysts adjusting forecasts and issuing procurement orders.
- **Viewers:** Read-only access to dashboards.

## Business Context
Curefoods operates multiple brands (EatFit, Nomad Pizza, etc.) across numerous cloud kitchens. To prevent stockouts and minimize food waste, the company needs to accurately predict how many raw ingredients to procure. 

The system achieves this by:
1. Analyzing historical POS dish sales (UrbanPiper).
2. Analyzing historical raw ingredient consumption (SupplyNote).
3. Applying forecasting logic to predict future demand.
4. Flagging variances where actual consumption heavily differs from forecasted/recipe-expected consumption (indicating waste, theft, or recipe non-compliance).
