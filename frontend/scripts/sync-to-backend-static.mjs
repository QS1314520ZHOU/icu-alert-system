import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendDir = path.resolve(__dirname, '..')
const distDir = path.join(frontendDir, 'dist')
const backendStaticDir = path.resolve(frontendDir, '..', 'backend', 'static')

if (!existsSync(distDir)) {
  console.error(`[sync-static] frontend dist not found: ${distDir}`)
  process.exit(1)
}

if (!existsSync(path.dirname(backendStaticDir))) {
  console.log(`[sync-static] backend directory not found, skipping sync: ${backendStaticDir}`)
  process.exit(0)
}

rmSync(backendStaticDir, { recursive: true, force: true })
mkdirSync(backendStaticDir, { recursive: true })
cpSync(distDir, backendStaticDir, { recursive: true, force: true })

console.log(`[sync-static] synced frontend dist to ${backendStaticDir}`)
