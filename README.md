# Panorama Global News

Portal de noticias con React + TanStack Start. El sitio muestra todas las noticias guardadas en `src/data/news.json`; el actualizador obtiene hasta 6 noticias nuevas por cada fuente RSS en cada ejecución y conserva hasta 150 noticias.

## Compilar
Desde la carpeta raíz del proyecto:
```sh
npm install
npm run build
```

## Actualización automática
- Workflow: `.github/workflows/actualizar_noticias.yml` (cada 4 horas, además de ejecución manual).
- En GitHub, abre **Actions → Actualizar Noticias Virales → Run workflow** para probarlo.
- El bot funciona con RSS aun sin clave de OpenAI. Si agregas `OPENAI_API_KEY` en **Settings → Secrets and variables → Actions**, podrá traducir y redactar los textos con IA.
- El repositorio debe permitir GitHub Actions escribir en el repositorio: **Settings → Actions → General → Workflow permissions → Read and write permissions**.
- El workflow asume que los archivos del proyecto están en la raíz del repositorio y actualiza automáticamente la rama predeterminada donde se ejecuta.

## Cloudflare Pages
Sube al repositorio los archivos y carpetas extraídos de este ZIP (no el ZIP como único archivo). En Pages, el directorio raíz debe quedar vacío; comando de compilación `npm run build`. Usa el directorio de salida que indique el registro de compilación de TanStack/Vite para esta configuración.
