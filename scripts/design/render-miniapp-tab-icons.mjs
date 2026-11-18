/**
 * Export the installed NutUI SVGs to native TabBar PNGs.
 * Renderer is a development tool supplied explicitly; no app dependency is added.
 */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdtemp, rename, lstat } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const { values } = parseArgs({ options: { 'sharp-root': { type: 'string' }, check: { type: 'boolean', default: false } } })
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const app = join(root, 'apps/miniapp')
const requireFromApp = createRequire(join(app, 'package.json'))
const sharpPath = values['sharp-root']
  ? requireFromApp.resolve('sharp', { paths: [resolve(values['sharp-root'])] })
  : requireFromApp.resolve('sharp')
const sharp = requireFromApp(sharpPath)
const manifest = JSON.parse(await readFile(join(app, 'src/tab-bar.json'), 'utf8'))
const packageFile = requireFromApp.resolve('@nutui/icons-react-taro/package.json')
const installed = JSON.parse(await readFile(packageFile, 'utf8'))
const declared = JSON.parse(await readFile(join(app, 'package.json'), 'utf8')).dependencies['@nutui/icons-react-taro']
assert.equal(installed.version, declared, 'Installed NutUI version must equal the pinned app dependency')
assert.equal(manifest.items.length, 4, 'Expected four native tabs')
for (const color of [manifest.color, manifest.selectedColor]) assert.match(color, /^#[0-9a-f]{6}$/i)
const target = join(app, 'src/assets')
assert(!(await lstat(target)).isSymbolicLink(), 'Asset directory must not be a link')
const outputs = []
const sourceFiles = new Map()
const names = new Set()
for (const item of manifest.items) {
  assert.match(item.asset, /^[a-z]+$/)
  assert.match(item.icon, /^[A-Z][A-Za-z0-9]+$/)
  assert(!names.has(item.asset), 'Tab asset names must be unique')
  names.add(item.asset)
  const iconFile = join(dirname(packageFile), `dist/es/icons/${item.icon}.js`)
  const source = await readFile(iconFile, 'utf8')
  sourceFiles.set(iconFile, source)
  const matches = [...source.matchAll(/svg64: "data:image\/svg\+xml;base64,([A-Za-z0-9+/=]+)"/g)]
  assert.equal(matches.length, 1, `Expected one embedded SVG for ${item.icon}`)
  const svg = Buffer.from(matches[0][1], 'base64').toString('utf8')
  assert.match(svg, /^<svg\b/)
  assert(!/<(?:script|image|use)\b|(?:href|style)=/i.test(svg), 'Unexpected external or styled SVG content')
  for (const [suffix, color] of [['', manifest.color], ['-active', manifest.selectedColor]]) {
    const colored = svg.replace(/fill="(?!none")[^"]*"/g, `fill="${color}"`)
    assert.notEqual(colored, svg, 'Expected a recolorable NutUI fill')
    const bytes = await sharp(Buffer.from(colored), { density: 192 })
      .resize(65, 65, { fit: 'contain', background: '#00000000' })
      .extend({ top: 8, bottom: 8, left: 8, right: 8, background: '#00000000' })
      .png({ compressionLevel: 9 }).toBuffer()
    const metadata = await sharp(bytes).metadata()
    const { channels } = await sharp(bytes).ensureAlpha().stats()
    assert(metadata.width === 81 && metadata.height === 81 && metadata.hasAlpha, 'Expected transparent 81px PNG')
    assert(channels[3].min === 0 && channels[3].max > 0, 'PNG must contain visible pixels and transparent space')
    assert(bytes.length < 40 * 1024, 'Tab icon exceeds the platform size limit')
    const path = join(target, `tab-${item.asset}${suffix}.png`)
    assert(!(await lstat(path)).isSymbolicLink(), 'Refuse to replace linked assets')
    outputs.push({ path, bytes, original: await readFile(path) })
  }
}
if (values.check) {
  for (const { path, bytes, original } of outputs) assert(bytes.equals(original), `Generated icon drift: ${path}`)
  console.log(`Verified ${outputs.length} PNGs against NutUI ${installed.version}, sharp ${sharp.versions.sharp}`)
} else {
  // Validate/render everything before touching existing files, and retain original bytes.
  const backup = await mkdtemp(join(tmpdir(), 'pinjie-tab-icons-'))
  console.log(`Original PNG backup: ${backup}`)
  for (const { path, original } of outputs) {
    const filename = path.slice(target.length + 1)
    await writeFile(join(backup, filename), original, { flag: 'wx' })
    assert((await readFile(join(backup, filename))).equals(original), 'Backup verification failed')
    assert((await readFile(path)).equals(original), 'Asset changed during generation')
  }
  for (const [path, source] of sourceFiles) assert.equal(await readFile(path, 'utf8'), source, 'NutUI source changed during generation')
  for (const { path, bytes, original } of outputs) {
    assert((await readFile(path)).equals(original), 'Asset changed before replacement')
    const temporary = `${path}.tmp`
    await writeFile(temporary, bytes, { flag: 'wx' })
    await rename(temporary, path)
    assert((await readFile(path)).equals(bytes), 'Written PNG differs from rendered bytes')
    console.log(`${path.slice(root.length + 1)} ${bytes.length} bytes ${createHash('sha256').update(bytes).digest('hex')}`)
  }
  console.log(`Generated ${outputs.length} PNGs from NutUI ${installed.version}, sharp ${sharp.versions.sharp}`)
}
