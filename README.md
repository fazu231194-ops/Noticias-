# Panorama Global News

Portal de noticias (TanStack Start + React + Tailwind) que se actualiza solo: un workflow de GitHub Actions
lee feeds RSS, reescribe las notas con OpenAI y guarda el resultado en `src/data/news.json`.
Cada commit del bot dispara un nuevo despliegue en Cloudflare.

## Desarrollo local
```sh
npm install   # o bun install
npm run dev
npm run build
```

## Actualización automática de noticias
- Script: `scripts/fetch_news.py` · Workflow: `.github/workflows/actualizar_noticias.yml` (cada 4 h y manual).
- Requiere el secreto **OPENAI_API_KEY**: GitHub → Settings → Secrets and variables → Actions → New repository secret.
- Probar a mano: pestaña **Actions** → "Actualizar Noticias Virales" → **Run workflow**.
- Local: `pip install -r scripts/requirements.txt && OPENAI_API_KEY=sk-... python scripts/fetch_news.py`

## Despliegue en Cloudflare (Workers, con Git)
1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Import a repository** → elegí este repo.
2. Build command: `npm run build` (o `bun run build`).
3. Deploy command: `npx wrangler deploy`.
4. Cada push (incluidos los del bot) redespliega el sitio. Dominio propio: Worker → Settings → Domains & Routes.
