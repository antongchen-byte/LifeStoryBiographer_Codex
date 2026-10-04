# API schema boundary

The authoritative Pydantic request/response schemas live in `apps/api/app/schemas.py`.
FastAPI publishes their OpenAPI contract at `http://localhost:8000/openapi.json`.
The web app's currently consumed types are in `apps/web/lib/api.ts`.
Generate shared client types from OpenAPI when the next phase expands this contract;
do not maintain an independent competing domain schema here.
