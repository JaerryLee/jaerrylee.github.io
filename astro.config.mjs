import { defineConfig } from 'astro/config'

export default defineConfig({
  site: 'https://jaerrylee.github.io',
  output: 'static',
  trailingSlash: 'always',
  markdown: { shikiConfig: { theme: 'github-light' } },
})
