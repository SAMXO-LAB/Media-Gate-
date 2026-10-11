# Platform credentials

Each adapter reports exactly which variables are missing (`GET /api/platforms`, admin → Settings).
Until they're set, that platform shows **Not configured** — nothing is faked.

## YouTube — `YOUTUBE_API_KEY`
1. Google Cloud Console → create/select a project.
2. APIs & Services → Library → enable **YouTube Data API v3**.
3. Credentials → Create credentials → API key. Restrict it: *API restrictions* → YouTube Data API v3;
   *Application restrictions* → IP addresses of your API servers.
4. Default quota is 10,000 units/day; `videos.list` costs 1 unit. Results are cached 10 minutes.

There is no download credential to obtain: YouTube's Terms of Service only permit downloading through a
download link or button YouTube itself provides, so MediaGate shows metadata only.

## Instagram — `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`
Uses **Instagram API with Instagram Login** (Business Login for Instagram). Users need an Instagram
**Business or Creator** account; personal accounts aren't supported by Meta's API.

1. developers.facebook.com → My Apps → Create app → use case *Manage messaging & content on Instagram*
   (type Business).
2. Add product **Instagram** → *API setup with Instagram login*.
3. Business login settings → OAuth redirect URI:
   `https://<PUBLIC_API_URL host>/api/connections/instagram/callback`
4. Copy the **Instagram app ID** and **Instagram app secret** (these are distinct from the Facebook app ID).
5. Permissions: `instagram_business_basic` only.
6. In development mode only accounts added as testers (App roles → Instagram testers) can connect.
   For the public, submit **App Review** for `instagram_business_basic` and complete **Business Verification**.
   Your review submission should explain that the app lets account owners download their own media.

Behavior notes:
- Long-lived tokens last 60 days and are refreshed automatically when within 7 days of expiry.
- Media containing copyrighted material comes back without `media_url`; MediaGate shows it as withheld.
- Only the 500 most recent posts are searched when matching a link (`MAX_PAGES` in the adapter).

## X — `X_BEARER_TOKEN`, `X_CLIENT_ID`, optional `X_CLIENT_SECRET`
1. developer.x.com → Developer Console → create a Project and App.
2. Billing: new developers are on **pay-per-use** credits (since Feb 2026). Buy credits; each post read is
   billed. Check current rates at docs.x.com/x-api/getting-started/pricing. When credits run out the API
   returns errors that MediaGate surfaces as `platform_billing`.
3. Keys and tokens → **Bearer Token** → `X_BEARER_TOKEN` (used for public metadata).
4. User authentication settings → enable **OAuth 2.0**; type *Web App* (confidential → also set
   `X_CLIENT_SECRET`) or *Native/Single page* (public client, PKCE only).
   Callback URL: `https://<PUBLIC_API_URL host>/api/connections/x/callback`.
   Website URL: your frontend. Scopes requested: `tweet.read users.read offline.access`.
5. Copy **Client ID** → `X_CLIENT_ID`.

Policy: downloads are enabled only when the connected X account is the post's author.

## Supabase
- **SUPABASE_URL / anon key**: Settings → API.
- **SUPABASE_SERVICE_ROLE_KEY**: Settings → API keys → secret/service role. Server only.
- **JWT verification**: projects on asymmetric signing keys need nothing extra (JWKS is fetched from
  `SUPABASE_URL/auth/v1/.well-known/jwks.json`). Legacy projects set `SUPABASE_JWT_SECRET`.
- **DATABASE_URL**: Connect → *Session pooler* (IPv4) or direct connection. The transaction pooler (6543)
  also works (statement cache is disabled), but the worker's LISTEN/NOTIFY wake-up needs a session
  connection — with 6543 the worker falls back to 5-second polling.
- **Auth → URL configuration**: Site URL = frontend; add `https://<frontend>/auth/callback` to redirect URLs.
- **Auth → Email**: configure custom SMTP for production magic links.
