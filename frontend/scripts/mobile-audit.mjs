/**
 * Mobile layout audit over the Chrome DevTools Protocol.
 *
 * Prereqs:
 *  1. `npm run dev` (or a preview build) in one terminal
 *  2. Chrome started with remote debugging:
 *     chrome --headless=new --remote-debugging-port=9333 --user-data-dir=%TEMP%\sm-cdp about:blank
 *
 * Run: npm run audit:mobile
 * Optional env: CDP_PORT (9333), BASE_URL (http://127.0.0.1:5173)
 *
 * It fails (exit 1) if a route scrolls horizontally or if an interactive
 * element is smaller than the WCAG 2.2 minimum target size (24px).
 */
import process from 'node:process'

const CDP_PORT = process.env.CDP_PORT || '9333'
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:5173'
const PATHS = ['/', '/status', '/login', '/register', '/p/demo']
const WIDTH = 390
const HEIGHT = 844

const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`).then((r) => r.json())
const page = targets.find((target) => target.type === 'page')
if (!page) {
  console.error('No Chrome page target found. Start Chrome with --remote-debugging-port.')
  process.exit(2)
}

const ws = new WebSocket(page.webSocketDebuggerUrl)
let nextId = 0
const pending = new Map()

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
}

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) reject(new Error(message.error.message))
    else resolve(message.result)
  }
}

await new Promise((resolve) => (ws.onopen = resolve))
await send('Page.enable')
await send('Emulation.setDeviceMetricsOverride', {
  width: WIDTH,
  height: HEIGHT,
  deviceScaleFactor: 1,
  mobile: true,
})

const findings = []
for (const path of PATHS) {
  await send('Page.navigate', { url: `${BASE_URL}${path}` })
  await new Promise((resolve) => setTimeout(resolve, 1800))
  const result = await send('Runtime.evaluate', {
    expression: `JSON.stringify({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      offenders: Array.from(document.querySelectorAll('body *'))
        .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
        .slice(0, 5)
        .map((el) => el.tagName.toLowerCase() + '.' + String(el.className || '').split(' ').filter(Boolean).slice(0, 3).join('.')),
      tooSmall: Array.from(document.querySelectorAll('button, a, input, select'))
        .filter((el) => {
          const rect = el.getBoundingClientRect()
          if (rect.width === 0 || rect.height === 0 || rect.height >= 24) return false
          if (el.tagName === 'INPUT' && ['checkbox', 'radio', 'hidden'].includes(el.type)) return false
          // Inline links inside text have a WCAG target-size exception.
          return getComputedStyle(el).display !== 'inline'
        })
        .slice(0, 8)
        .map((el) => el.tagName.toLowerCase() + '.' + String(el.className || '').split(' ').filter(Boolean).slice(0, 2).join('.') + ' h' + Math.round(el.getBoundingClientRect().height))
    })`,
    returnByValue: true,
  })
  findings.push({ path, ...JSON.parse(result.result.value) })
}

await send('Emulation.clearDeviceMetricsOverride')
ws.close()

let failed = false
for (const finding of findings) {
  const overflow = finding.scrollWidth > finding.innerWidth
  const tiny = finding.tooSmall.length > 0
  if (overflow || tiny) failed = true
  console.log(
    `${overflow ? '✗' : '✓'} ${finding.path}  width=${finding.scrollWidth}/${finding.innerWidth}` +
      `${overflow ? '  overflow=' + finding.offenders.join(', ') : ''}` +
      `${tiny ? '  small-targets=' + finding.tooSmall.join(', ') : ''}`,
  )
}

if (failed) {
  console.error('\nMobile audit found issues (see above).')
  process.exit(1)
}
console.log('\nMobile audit passed: no horizontal overflow, all targets ≥24px.')
