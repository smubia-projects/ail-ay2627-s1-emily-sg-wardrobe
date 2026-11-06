# SG Wardrobe

A mobile-friendly AI personal stylist for Singapore, by Emily Gan (AI Lodge AY26/27 S1).
Live demo: **<https://ail-ay2627-s1-emily-sg-wardrobe.vercel.app/>**

## Problem Statement

Deciding what to wear takes far too long. Many of us change in and out of
outfits every morning because nothing feels quite right, and talking to friends
showed this is a shared daily frustration. Singapore makes it harder: an outfit
has to survive a hot, humid walk outside, sudden rain, haze days and 19°C office
or classroom aircon, all in the same day.

Shopping has the same problem. Fashion isn't one-size-fits-all: what looks
great on a model or a friend can look completely different on us, because we
all come in different shapes and sizes. Buying clothes online often ends in
disappointment and tedious returns.

This is worth solving because it affects people every day. A better system
helps people get more out of clothes they already own, buy fewer pieces that
don't fit, and send back less, which saves time and money and creates less
waste.

## Solution Overview

SG Wardrobe takes the guesswork out of getting dressed and shopping:

1. People add the clothes they already own to a digital closet, with photos.
2. They enter their body measurements and match their skin shade against an
   on-screen chart.
3. The AI uses the closet, the measurements, the occasion and Singapore's
   conditions to suggest complete outfits from clothes they already have,
   explain their body shape and best colours, and review which pieces suit them.
4. Before buying something online, they paste the shop's size chart (and,
   optionally, the product link). The AI says which size to buy, how it will
   fit, and how well it matches their wardrobe.

This public demo has no accounts: every visitor starts with a sample closet,
and anything they add (photos included) stays in their own browser.

## Key Features

- **Digital closet:** add clothes with photos (the background is removed in the
  browser), category, colour, fabric, breathability, formality, and whether a
  piece is rain-safe or works as an aircon layer.
- **Weather-aware outfit ideas:** complete outfits (top and bottom or a dress,
  shoes, and optionally a layer and accessories) for preset occasions (Work fit,
  Classroom comfy, Outdoors) or any occasion the user types in, such as "Wedding
  lunch" or "Beach day at Sentosa".
- **Live weather and haze:** the Today page shows Singapore's current
  temperature, feels-like temperature, humidity, the 2-hour and 24-hour
  forecasts, and the PSI and PM2.5 haze readings, all from the official
  Meteorological Service Singapore / National Environment Agency feeds. Outfit
  suggestions are generated for these real conditions (for example rain-safe
  shoes when showers are forecast).
- **Body shape and colour analysis:** from measurements and skin shade, the AI
  identifies body shape (hourglass, pear, inverted triangle, rectangle or apple)
  and suggests flattering colours, colours to avoid, and cuts and silhouettes.
- **Wardrobe review:** "What stays, what goes": each piece is checked against
  the user's measurements and the heat.
- **Smart shopping size check:** paste the shop's size chart (the most reliable
  input) and optionally the product link, to get the size to buy, a fit check by
  body area (good / snug / loose) and a wardrobe match score, with pieces from
  the closet it pairs with.
- **No sign-in:** the closet, measurements, shopping check and review are kept
  in the browser's local storage. Settings can reset everything to the sample
  closet.

## AI Integration

All AI features go through [OpenRouter](https://openrouter.ai/) (default model
`gemini-3.5-flash-lite`, set with `MODEL_NAME`). The browser never talks
to the model directly: it sends **structured data** (task type, closet list,
measurements, live conditions) to a small FastAPI service on Google Cloud Run
(`backend/`), which builds the prompt itself, holds the API key and calls
OpenRouter. The endpoint cannot be used as a general-purpose AI proxy.

| Feature | What the browser sends (`POST /api/style`) | What comes back |
|---|---|---|
| Outfit ideas (`task: outfits`) | The occasion, the outfits already on screen, the closet list (name, category, colour, fabric, breathability, formality, rain-safe, aircon layer) and live NEA readings (temperature, feels-like, humidity, 2-hour and 24-hour forecast, PSI and PM2.5) | Outfits as JSON, each listing closet item IDs and a short reason |
| Body shape & colours (`task: profile`) | Height, shoulder, bust, waist, hips, leg length, weight, frame, chosen skin shade, closet list | Body shape, flattering colours, colours to avoid, silhouettes, materials and three looks |
| Wardrobe review (`task: review`) | Measurements, style-profile summary, closet list | Which pieces to keep, restyle or let go, and what to buy next |
| Size check (`task: shop`) | Measurements, style-profile summary, the pasted size chart, text read from the shop page if a link was given (`POST /api/product`), closet list | Recommended size, confidence, fit by body area, match score, closet pieces it pairs with |

The app never shows the model's text as-is: it checks every answer before
displaying it (see **Guardrails** below). When no API key is set, the API
answers `GET /api/style` with `{"ai": false}` and the site switches its AI
features off; everything else keeps working.

## External Tools & Datasets

| Tool / dataset | Used for |
|---|---|
| [apiyi](https://apiyi.com) (default `gemini-3.5-flash-lite`) | Outfit ideas, body shape and colour analysis, wardrobe review, size and fit checks |
| [FastAPI](https://fastapi.tiangolo.com/) on [Google Cloud Run](https://cloud.google.com/run) | The API in `backend/` |
| [Upstash Redis](https://upstash.com/) | The shared AI Lodge rate limiter on the AI route |
| [data.gov.sg real-time API](https://data.gov.sg/) (Meteorological Service Singapore / NEA): air temperature, relative humidity, 2-hour and 24-hour forecasts, PSI and PM2.5 | Live weather and haze on the Today page and in outfit prompts. Called from the browser; free and needs no API key |
| [@imgly/background-removal](https://www.npmjs.com/package/@imgly/background-removal) (AGPL-3.0) | Removing photo backgrounds in the browser, so photos never leave the device |
| [Vercel](https://vercel.com/) | Hosting the static site in `frontend/` |
| Google Fonts | Fonts |
| Claude Code (in VS Code), Gemini, GitHub | Building and planning the app, version control |

The app does not use any training dataset. The sample closet photos are
embedded in `frontend/index.html` or bundled in `frontend/assets/`.

## Project Layout

```
frontend/   static site for Vercel: index.html, assets/, build.js -> config.js (VITE_API_BASE)
backend/    FastAPI API for Cloud Run: app/main.py, prompts.py, llm.py, product_reader.py, rate limiting
.github/workflows/deploy.yml   builds backend/ and deploys it to Cloud Run on push to main
```

## Run Locally

```bash
# 1. API (Python 3.11+)
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export API_KEY=...                       # optional: without it AI is switched off
export CORS_ORIGINS=http://localhost:8000
uvicorn app.main:app --port 8001

# 2. Site (another terminal)
cd frontend
node build.js                                       # writes config.js -> http://localhost:8001
python -m http.server 8000                          # open http://localhost:8000
```

`GET http://localhost:8001/api/health` returns `{"status":"ok"}`. Rate limiting
is off unless the Upstash variables are set. Every backend variable is listed
in `.env.example`.

## Deploy (AI Lodge stack)

- **Backend → Cloud Run:** fill `.env` from `.env.example`, upload it with
  `gh secret set DOTENV --repo smubia-projects/ail-ay2627-s1-emily-sg-wardrobe < .env`,
  then push to `main` (or `gh workflow run deploy.yml`). The workflow builds
  `backend/`, pushes it to Docker Hub and deploys service
  `ail-ay2627-s1-emily-sg-wardrobe` in `asia-southeast3`
  (`https://ail-ay2627-s1-emily-sg-wardrobe-464725632804.asia-southeast3.run.app`).
- **Frontend → Vercel:** import the repo, set the root directory to `frontend`,
  and set `VITE_API_BASE` to the Cloud Run URL. `vercel.json` runs
  `npm run build` and serves the folder as a static site.
- **CORS:** `CORS_ORIGINS` must contain the Vercel URL
  (`https://ail-ay2627-s1-emily-sg-wardrobe.vercel.app`).
- **Rate limit:** the AI route uses the club's shared engine with one bucket,
  `style` (fallbacks `RATE_LIMIT_STYLE_MAX`, `RATE_LIMIT_WINDOW_SECONDS`). Over
  the limit the site shows the AI Lodge call-to-action; when the demo is paused
  centrally it shows a "demo paused" notice instead.

## AI Safety & Limitations

### Risks and limitations

- **Size and fit predictions can be wrong.** They depend on the user measuring
  themselves accurately and on the shop publishing a correct size chart. When
  no chart is found, the AI says so and marks its confidence as low. Treat the
  advice as guidance, not a guarantee.
- **Weather is island-wide, not hyper-local.** Temperature and humidity are
  averaged across NEA's weather stations, and the "feels like" value is a heat
  index calculated from them. Conditions at a particular street can differ. If
  the weather feed cannot be reached, the app says so and the AI falls back to a
  typical Singapore day (about 31°C, humid, chance of showers).
- **Colour analysis is approximate.** Skin shade is matched by eye against a
  screen, and screens and lighting vary.
- **Body shape labels are generalisations.** They describe proportions and are
  not a judgement of anyone's body. The app gives styling suggestions, not
  rules.
- **Personal data is sent to a third party.** Measurements and closet details
  are sent through OpenRouter to the model provider to generate answers. Closet
  photos are not sent to the AI.
- **Data lives in one browser.** There are no accounts. Closet photos and
  measurements are stored in the browser's local storage: they are lost when
  site data is cleared and do not follow the user to another device. Local
  storage is small (about 5 MB), so a few dozen added photos can fill it; the
  app warns when that happens.
- **Shop pages vary.** Many shops block automated reading (especially from
  cloud servers) or load sizes with scripts, so the pasted size chart is the
  primary input and the shop link is only a best-effort extra.
- **Cost.** Every AI request costs money. The AI route is rate limited per
  IP by the AI Lodge limiter, and the club can pause the demo centrally.

### Guardrails implemented

- **Structured requests only.** `POST /api/style` accepts one of four task
  types with validated, length-capped fields (closet of at most 200 items,
  names of at most 80 characters, a size chart of at most 4,000 characters,
  bodies of at most 100 KB). The prompt is assembled on the server, and text
  the user typed or that came from a shop page is fenced off and labelled as
  untrusted.
- **The API key stays on the server.** It is read from Cloud Run's environment
  and is never sent to the browser.
- **Rate limiting.** The shared AI Lodge limiter counts AI requests per IP;
  shop-page reads (no AI) have their own small flood guard.
- **Every AI answer is checked before it is shown.** Outfits must use real items
  from the user's closet and have a valid combination (one top and one bottom or
  one dress, plus shoes; a layer must be marked as an aircon layer). Outfits
  that fail these checks are dropped. Shopping results must have a size and a
  0–100 score, and all AI text is length-limited and shown as plain text, not
  HTML.
- **Heat rules in the prompt.** The prompt tells the AI to judge heat honestly,
  for example no layers, denim, wool, leather or boots for Outdoors, and to
  prefer breathable fabrics.
- **Refusals and errors are handled.** If the AI declines, is busy, times out
  or replies with something other than JSON (retried once on the server), the
  user sees a clear message and their outfits stay unchanged.
- **Safe link reading.** The shop page reader only fetches public `http(s)`
  addresses (also after redirects), never private or local network addresses.
- **Private data.** Nothing is stored on the server: the API keeps no
  database and no logs of closet contents. Photos never leave the browser.
- **Spend control.** The app runs with AI switched off when no key is
  configured, and OpenRouter spend can be capped on the key.

### Testing

The student's testing below was done on the original Supabase + Anthropic
version; the AI Lodge port was re-checked with a stubbed model.


- Tested the live site with several accounts, checking that each person's
  closet, measurements and review stay separate and persist after signing out
  and back in.
- Tested every AI feature (outfit ideas, body shape and colour analysis,
  wardrobe review and the shopping link analyzer) on both the local server and
  the live Vercel deployment.
- Tested the app with AI switched off (no API key) to confirm the closet,
  measurements and settings still work and the AI buttons show a clear message.
- Tested error cases, including a missing or invalid API key and an account
  with no credits, to confirm the app shows an error instead of breaking.
