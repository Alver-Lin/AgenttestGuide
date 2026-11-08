import { createRequire } from 'node:module'
import { mkdtempSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

// Use the TypeScript bundler already supplied by Vite, without adding a test runtime.
const require = createRequire(import.meta.resolve('vite'))
const directory = mkdtempSync(join(tmpdir(), 'agenttestguide-tests-'))
try {
  const tests = readdirSync('tests').filter((name) => name.endsWith('.test.ts'))
  require('esbuild').buildSync({
    entryPoints: tests.map((name) => join('tests', name)),
    outdir: directory,
    outExtension: { '.js': '.cjs' },
    bundle: true,
    platform: 'node',
    format: 'cjs',
    logLevel: 'silent',
  })
  const result = spawnSync(
    process.execPath,
    ['--test', ...tests.map((name) => join(directory, name.replace(/\.ts$/, '.cjs')))],
    { stdio: 'inherit' },
  )
  if (result.error) throw result.error
  process.exitCode = result.status ?? 1
} finally {
  rmSync(directory, { recursive: true, force: true })
}
