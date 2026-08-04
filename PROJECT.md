# Project: Collaboration Operations Platform

## Architecture
The Collaboration Operations Platform is a multi-tier, multi-service monorepo application:
- **Frontend App Router (`apps/web`)**: Next.js 16 / React 19 web application providing persona-specific views (Owner Console, Client Portal, Public Portal, Marketplace Catalog) consuming API endpoints.
- **Backend REST API (`apps/api`)**: FastAPI (Python 3.14) & Fastify / Cloudflare Worker (TS/JS) API server providing REST endpoints, OAuth2 token authority, SCIM directory sync, and webhook ingress/egress.
- **Shared Packages (`packages/`)**: Core domain logic including Zod models (`packages/domain`), DB schemas & atomic job queues (`packages/database`), ABAC policy engine (`packages/policy`), encrypted object storage (`packages/object-store`), full-text search (`packages/search`), state workflows (`packages/workflows`), OAuth2/SAML auth (`packages/auth`), and webhook egress (`packages/webhooks`).
- **CI Verification Gates (`scripts/gates/packets/`, `scripts/omega.sh`)**: Executable bash gate scripts asserting live runtime API status, DB state transitions, and auth claims for system-wide fixed-point verification.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | API Task Endpoints | Real DB operations for GET/POST /api/tasks, assign, verify, archive | M1 | R2 / SCHEMA.md |
| 2 | OAuth2 Flow | Full authorization code & client credentials flows with token authority | M1 | R2 / packages/auth |
| 3 | Webhook Ingress & Egress | Signed RFC8785 JSON digest egress with transactional outbox & ingress verification | M1 | R2 / apps/api |
| 4 | SCIM Directory Sync | SCIM 2.0 provisioning & directory sync endpoints | M1 | R2 / apps/api/scim.ts |
| 5 | Database Integration | Wire API endpoints to PostgreSQL / D1 SQLite schemas & Drizzle ORM | M1 | R2 / packages/database |
| 6 | Client Dashboard UI | Polished React dashboard view with token-gated task status & metrics | M2 | R1 / apps/web |
| 7 | Marketplace Catalog UI | Interactive React catalog browsing, app install, task submission form | M2 | R1 / apps/web |
| 8 | Admin Steering Console UI | Owner task board, recovery, verification, assignment, and archive queues | M2 | R1 / apps/web |
| 9 | Public Portal UI | Public-facing aggregate metrics display | M2 | R1 / apps/web |
| 10 | Functional CI Gate Scripts | Rewrite scripts/gates/packets/*.sh to test real HTTP requests & DB state | M3 | R3 / scripts/gates/ |
| 11 | Omega Fixed Point Verification | Ensure scripts/omega.sh double zero-diff run passes completely | M3 | R3 / scripts/omega.sh |
| 12 | Automated UI Smoke Verification | Automated test script asserting UI loads without crash & renders catalog | M3 | Acceptance Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Backend Business Logic & API/Database/Webhook/OAuth | Active DB routes, OAuth2, webhook egress/ingress, SCIM sync in `apps/api` and `packages/` | none | DONE |
| M2 | Frontend React UI Upgrade | Interactive React UI in `apps/web` (Dashboard, Marketplace, Admin Console, Public Portal) | M1 | IN_PROGRESS |
| M3 | Functional CI Gates & Omega Verification | Functional packet gate scripts in `scripts/gates/packets/` & passing `scripts/omega.sh` fixed point | M1, M2 | PLANNED |


## Interface Contracts

### Backend API ↔ Database & Packages
- **Task Management**: `GET /api/tasks`, `POST /api/tasks`, `POST /api/tasks/{id}/assign`, `POST /api/tasks/{id}/verify`, `POST /api/tasks/{id}/archive` consume Zod schemas from `packages/domain` & query `packages/database`.
- **Authorization**: Persona checks via `LIMEN_OWNER_TOKEN`, `LIMEN_CLIENT_TOKEN`, and public authorization headers.
- **Webhook Egress**: `deliverWebhook(payload, secret)` in `packages/webhooks` constructs RFC8785 canonical JSON digest, signs payload, posts via HTTP, handles retries.

### Frontend App ↔ Backend API
- `NEXT_PUBLIC_API_URL` environment variable points to API server (`http://localhost:8000`).
- Dashboard & Marketplace React components fetch from `/api/tasks`, `/api/client-status`, `/api/public-status`, and submit tasks via `POST /api/tasks`.

### CI Gates ↔ API & Database
- Packet gate scripts (`scripts/gates/packets/*.sh`) execute `curl` against local API server, assert HTTP status codes (200/201/202), parse JSON responses, verify database records in `tasks.yaml` / PostgreSQL / D1.

## Code Layout
- **M1 Ownership**: `apps/api/**/*`, `packages/auth/**/*`, `packages/webhooks/**/*`, `packages/database/**/*`
- **M2 Ownership**: `apps/web/**/*`
- **M3 Ownership**: `scripts/gates/packets/**/*`, `scripts/omega.sh`, `scripts/verify-ui.sh` (or test runner scripts)
