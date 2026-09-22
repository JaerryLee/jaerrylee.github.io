import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const portfolio = fileURLToPath(new URL('../../portfolio/', import.meta.url))
const output = new URL('../../portfolio/dist/', import.meta.url)
const destination = new URL('../public/portfolio/', import.meta.url)

if (!existsSync(new URL('../../portfolio/package.json', import.meta.url))) {
  throw new Error('Place the portfolio checkout beside this blog before syncing.')
}

const build = spawnSync('pnpm', ['build'], {
  cwd: portfolio,
  env: { ...process.env, GITHUB_ACTIONS: 'true', VITE_BLOG_URL: 'https://jaerrylee.github.io' },
  stdio: 'inherit',
})
if (build.error) throw build.error
if (build.status !== 0) process.exit(build.status ?? 1)
if (!existsSync(new URL('index.html', output)) || !existsSync(new URL('en/index.html', output))) {
  throw new Error('The portfolio build must include both Korean and English entry pages.')
}

rmSync(destination, { recursive: true, force: true })
mkdirSync(destination, { recursive: true })
cpSync(output, destination, { recursive: true })
console.log('Updated public/portfolio with the built portfolio site.')
