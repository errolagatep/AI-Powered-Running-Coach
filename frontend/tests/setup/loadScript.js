/**
 * Loads a vanilla browser JS file into an isolated vm context with minimal
 * browser globals mocked. Returns the context object — any functions defined
 * at the module level (not inside event handlers) are accessible as properties.
 *
 * Usage:
 *   const ctx = loadScript('auth.js')
 *   ctx.formatPace(5.5)  // => "5:30"
 *
 * Pass multiple filenames to load them in order into the same context (e.g.
 * auth.js must be loaded before training_plan.js because the latter calls
 * `escapeHtml` and `effortClass` which are defined in auth.js).
 */

import vm from 'vm'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const JS_DIR = path.resolve(__dirname, '../../js')

function makeBrowserContext() {
  const store = {}
  const localStorage = {
    getItem: k => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: k => { delete store[k] },
  }

  // Minimal DOM stubs — only what the scripts need during their top-level
  // evaluation (i.e. registering listeners, not running them).
  const makeElement = () => ({
    classList: {
      add() {}, remove() {}, toggle() {}, contains: () => false,
    },
    style: {},
    innerHTML: '',
    textContent: '',
    dataset: {},
    value: '',
    appendChild() {},
    querySelector: () => null,
    querySelectorAll: () => [],
  })

  const document = {
    addEventListener: () => {},
    getElementById: () => makeElement(),
    querySelector: () => makeElement(),
    querySelectorAll: () => [],
    createElement: () => makeElement(),
    body: { appendChild() {} },
  }

  // flatpickr is called at top-level in dashboard.js — must return an object.
  const flatpickr = () => ({ set() {}, setDate() {}, destroy() {} })

  const ctx = {
    window: null,
    document,
    localStorage,
    location: { pathname: '/', href: '' },
    flatpickr,
    lucide: { createIcons() {} },
    // api stub — async functions that return null so they never block
    api: {
      get: async () => null,
      post: async () => null,
      patch: async () => null,
      delete: async () => null,
    },
    Icons: {
      dumbbell: '🏋️',
      flame: '🔥',
      star: '⭐',
      trendingUp: '📈',
      sunrise: '🌅',
    },
    alert: () => {},
    // Standard JS globals
    console,
    Date, Math, String, Number, Boolean, Array, Object, JSON,
    parseInt, parseFloat, isNaN, isFinite, NaN, Infinity,
    Symbol, RegExp, Set, Map, WeakMap, WeakSet,
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
    Promise, Error, TypeError, RangeError, ReferenceError, SyntaxError,
    undefined,
  }
  ctx.window = ctx
  return vm.createContext(ctx)
}

/**
 * Load one or more JS source files into a fresh browser context.
 * Files are evaluated in the order provided.
 */
export function loadScript(...filenames) {
  const ctx = makeBrowserContext()
  for (const filename of filenames) {
    const code = fs.readFileSync(path.join(JS_DIR, filename), 'utf8')
    vm.runInContext(code, ctx)
  }
  return ctx
}
