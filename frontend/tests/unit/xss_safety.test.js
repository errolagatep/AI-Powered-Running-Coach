/**
 * Tests verifying XSS safety of HTML rendering functions.
 *
 * Bugs caught are marked [BUG].
 *
 * The key invariant: any user-controlled string (name, avatar_url, AI-generated
 * notes) that ends up in innerHTML MUST be escaped with escapeHtml() first.
 * These tests verify that by calling the rendering functions with adversarial
 * input and checking the resulting innerHTML for raw HTML tags.
 */

import { describe, it, expect, beforeAll } from 'vitest'
import vm from 'vm'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const JS_DIR = path.resolve(__dirname, '../../js')

/**
 * Loads auth.js into an isolated context with a trackable navbar element.
 * Returns { ctx, navbarEl } where navbarEl.innerHTML records what was set.
 */
function loadAuthWithTrackableNavbar() {
  const store = {}
  const localStorage = {
    getItem: k => store[k] ?? null,
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: k => { delete store[k] },
  }

  const navbarEl = { innerHTML: '', classList: { add() {}, remove() {}, contains: () => false } }
  const navListEl = {
    querySelector: () => null,
    appendChild() {},
  }

  const document = {
    addEventListener: () => {},
    getElementById: (id) => {
      if (id === 'navbar-user') return navbarEl
      if (id === 'logout-btn') return { addEventListener() {} }
      return { innerHTML: '', textContent: '', classList: { add() {}, remove() {} }, style: {} }
    },
    querySelector: (sel) => {
      if (sel === '.navbar-nav') return navListEl
      return null
    },
    querySelectorAll: () => [],
    createElement: () => ({ innerHTML: '', classList: { add() {}, remove() {} } }),
    body: { appendChild() {} },
  }

  const ctx = {
    window: null, document, localStorage,
    location: { pathname: '/', href: '' },
    flatpickr: () => ({ set() {}, setDate() {}, destroy() {} }),
    lucide: { createIcons() {} },
    api: { get: async () => null, post: async () => null, patch: async () => null, delete: async () => null },
    Icons: {},
    alert: () => {},
    console,
    Date, Math, String, Number, Boolean, Array, Object, JSON,
    parseInt, parseFloat, isNaN, isFinite, NaN, Infinity,
    Symbol, RegExp, Set, Map, WeakMap, WeakSet,
    setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0, clearInterval: () => {},
    Promise, Error, TypeError, RangeError, ReferenceError, SyntaxError,
    undefined,
  }
  ctx.window = ctx

  const vmCtx = vm.createContext(ctx)
  const code = fs.readFileSync(path.join(JS_DIR, 'auth.js'), 'utf8')
  vm.runInContext(code, vmCtx)

  return { ctx: vmCtx, navbarEl }
}

// ── renderNavbarUser XSS safety ───────────────────────────────────────────────

describe('renderNavbarUser XSS safety (auth.js)', () => {
  const XSS_NAME = '<img src=x onerror="alert(1)">'
  const XSS_URL  = '" onerror="alert(1)"'

  // [BUG] Prior to fix, user.name was interpolated directly into innerHTML:
  //   `<span class="navbar-user-name">${user.name}</span>`
  // An attacker who sets their name to an HTML string could inject arbitrary
  // event handlers into every page that loads auth.js.
  it('[BUG] user.name with HTML tags must be escaped in the navbar', () => {
    const { ctx, navbarEl } = loadAuthWithTrackableNavbar()
    ctx.renderNavbarUser({ name: XSS_NAME, avatar_url: null })
    // Raw <img> tag must not appear (would be executable as HTML)
    expect(navbarEl.innerHTML).not.toContain('<img')
    // onerror= as an unescaped attribute must not appear
    expect(navbarEl.innerHTML).not.toMatch(/onerror\s*=\s*"alert/)
    // The escaped entity must be present instead
    expect(navbarEl.innerHTML).toContain('&lt;img')
  })

  it('[BUG] user.avatar_url with attribute-breaking chars must be escaped', () => {
    const { ctx, navbarEl } = loadAuthWithTrackableNavbar()
    ctx.renderNavbarUser({ name: 'Alice', avatar_url: XSS_URL })
    expect(navbarEl.innerHTML).not.toContain('onerror="alert')
    expect(navbarEl.innerHTML).toContain('&quot;')
  })

  it('safe name renders as plain text in the navbar', () => {
    const { ctx, navbarEl } = loadAuthWithTrackableNavbar()
    ctx.renderNavbarUser({ name: 'Jane Doe', avatar_url: null })
    expect(navbarEl.innerHTML).toContain('Jane Doe')
    expect(navbarEl.innerHTML).not.toContain('<script')
  })

  it('[BUG] initials derived from adversarial name must not produce raw HTML tags', () => {
    const { ctx, navbarEl } = loadAuthWithTrackableNavbar()
    // Name starts with '<' — naively the initial would be '<' which creates <? in the DOM.
    ctx.renderNavbarUser({ name: '<script> injection', avatar_url: null })
    const html = navbarEl.innerHTML
    // No raw '<script>' tag should appear anywhere
    expect(html).not.toMatch(/<script>/i)
    // The initials div must not contain a raw '<' (a non-alphanumeric initial is replaced with '?')
    expect(html).not.toMatch(/<div class="navbar-initials"></)
  })
})

// ── escapeHtml covers all HTML injection vectors ──────────────────────────────

describe('escapeHtml covers all XSS vectors', () => {
  let escapeHtml

  beforeAll(() => {
    const code = fs.readFileSync(path.join(JS_DIR, 'auth.js'), 'utf8')
    const ctx = vm.createContext({
      window: null, document: { addEventListener() {} }, localStorage: { getItem: () => null },
      location: { pathname: '/' }, console, Date, Math, String, Number, Boolean, Array, Object,
      JSON, parseInt, parseFloat, isNaN, isFinite, NaN, Infinity, Symbol, RegExp,
      Set, Map, WeakMap, WeakSet, setTimeout: () => 0, clearTimeout: () => {},
      setInterval: () => 0, clearInterval: () => {}, Promise, Error, TypeError,
      RangeError, ReferenceError, SyntaxError, undefined,
      flatpickr: () => ({}), lucide: { createIcons() {} }, api: {}, Icons: {}, alert: () => {},
    })
    vm.runInContext(code, ctx)
    escapeHtml = ctx.escapeHtml
  })

  it('escapes <script> tag completely', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('escapes onerror attribute injection', () => {
    const input = '" onerror="alert(1)"'
    const result = escapeHtml(input)
    expect(result).not.toContain('"')
    expect(result).toContain('&quot;')
  })

  it('escapes single-quote attribute injection', () => {
    const input = "' onmouseover='alert(1)'"
    const result = escapeHtml(input)
    expect(result).not.toContain("'")
    expect(result).toContain('&#x27;')
  })

  it('escapes all five special HTML characters', () => {
    expect(escapeHtml('&')).toBe('&amp;')
    expect(escapeHtml('<')).toBe('&lt;')
    expect(escapeHtml('>')).toBe('&gt;')
    expect(escapeHtml('"')).toBe('&quot;')
    expect(escapeHtml("'")).toBe('&#x27;')
  })

  it('leaves safe alphanumeric text unchanged', () => {
    expect(escapeHtml('Hello World 123')).toBe('Hello World 123')
  })

  it('handles null-like inputs without throwing', () => {
    expect(() => escapeHtml(null)).not.toThrow()
    expect(() => escapeHtml(undefined)).not.toThrow()
    expect(() => escapeHtml(0)).not.toThrow()
  })
})
