/**
 * Tests for pure utility functions defined in frontend/js/auth.js:
 *   formatPace, formatDistance, formatDuration, formatDate,
 *   escapeHtml, effortClass
 *
 * Bugs caught by this suite are marked [BUG].
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { loadScript } from '../setup/loadScript.js'

let ctx

beforeAll(() => {
  ctx = loadScript('auth.js')
})

// ── formatPace ───────────────────────────────────────────────────────────────

describe('formatPace', () => {
  it('formats whole minutes correctly', () => {
    expect(ctx.formatPace(5)).toBe('5:00')
    expect(ctx.formatPace(6)).toBe('6:00')
  })

  it('formats half minutes correctly', () => {
    expect(ctx.formatPace(5.5)).toBe('5:30')
    expect(ctx.formatPace(4.25)).toBe('4:15')
  })

  it('pads seconds to two digits', () => {
    expect(ctx.formatPace(6 + 5 / 60)).toBe('6:05')
  })

  it('handles sub-1-minute paces', () => {
    expect(ctx.formatPace(0.5)).toBe('0:30')
  })

  // [BUG] When the fractional part rounds to 60 seconds the function returns
  // "N:60" instead of "(N+1):00". Example: pace=5.999 → "5:60" not "6:00".
  it('[BUG] rounds seconds >= 60 into next minute', () => {
    expect(ctx.formatPace(5.999)).toBe('6:00')   // currently returns "5:60"
    expect(ctx.formatPace(3.9999)).toBe('4:00')  // currently returns "3:60"
  })
})

// ── formatDistance ───────────────────────────────────────────────────────────

describe('formatDistance', () => {
  it('returns integer string for whole numbers', () => {
    expect(ctx.formatDistance(5)).toBe('5')
    expect(ctx.formatDistance(10)).toBe('10')
    expect(ctx.formatDistance(0)).toBe('0')
  })

  it('returns two-decimal string for fractional values', () => {
    expect(ctx.formatDistance(5.1)).toBe('5.10')
    expect(ctx.formatDistance(21.097)).toBe('21.10')
  })

  it('treats 5.0 as whole number', () => {
    expect(ctx.formatDistance(5.0)).toBe('5')
  })
})

// ── formatDuration ───────────────────────────────────────────────────────────

describe('formatDuration', () => {
  it('formats minutes and seconds under an hour', () => {
    expect(ctx.formatDuration(30)).toBe('30:00')
    expect(ctx.formatDuration(1.5)).toBe('1:30')
    expect(ctx.formatDuration(59)).toBe('59:00')
  })

  it('formats hours correctly', () => {
    expect(ctx.formatDuration(60)).toBe('1:00:00')
    expect(ctx.formatDuration(90)).toBe('1:30:00')
    expect(ctx.formatDuration(125)).toBe('2:05:00')
  })

  it('pads minutes and seconds to two digits', () => {
    expect(ctx.formatDuration(61 + 5 / 60)).toBe('1:01:05')
  })

  it('handles zero duration', () => {
    expect(ctx.formatDuration(0)).toBe('0:00')
  })

  it('handles fractional seconds correctly', () => {
    // 59.983 min → 3599 sec → 59 min 59 sec
    expect(ctx.formatDuration(59.983)).toBe('59:59')
  })
})

// ── formatDate ───────────────────────────────────────────────────────────────

describe('formatDate', () => {
  it('formats ISO date string to readable form', () => {
    // "Jan 1, 2025" — note: Date constructor with ISO string uses UTC midnight,
    // so the result depends on the system timezone. We just assert shape.
    const result = ctx.formatDate('2025-06-15T12:00:00')
    expect(result).toMatch(/Jun/)
    expect(result).toMatch(/2025/)
  })
})

// ── escapeHtml ───────────────────────────────────────────────────────────────

describe('escapeHtml', () => {
  it('escapes ampersand', () => {
    expect(ctx.escapeHtml('a & b')).toBe('a &amp; b')
  })

  it('escapes angle brackets', () => {
    expect(ctx.escapeHtml('<script>')).toBe('&lt;script&gt;')
  })

  it('escapes double quotes', () => {
    expect(ctx.escapeHtml('"hello"')).toBe('&quot;hello&quot;')
  })

  it('leaves safe text unchanged', () => {
    expect(ctx.escapeHtml('hello world')).toBe('hello world')
  })

  it('coerces non-string input to string', () => {
    expect(ctx.escapeHtml(42)).toBe('42')
  })

  // [BUG] Single quotes are NOT escaped, making the function unsafe in HTML
  // attribute contexts like: <div onclick="fn('${value}')">
  it('[BUG] should escape single quotes for attribute safety', () => {
    expect(ctx.escapeHtml("it's")).toBe("it&#x27;s")  // currently returns "it's"
  })
})

// ── effortClass ──────────────────────────────────────────────────────────────

describe('effortClass', () => {
  it('returns effort-easy for low effort (1-4)', () => {
    expect(ctx.effortClass(1)).toBe('effort-easy')
    expect(ctx.effortClass(4)).toBe('effort-easy')
  })

  it('returns effort-mod for moderate effort (5-7)', () => {
    expect(ctx.effortClass(5)).toBe('effort-mod')
    expect(ctx.effortClass(7)).toBe('effort-mod')
  })

  it('returns effort-hard for high effort (8-10)', () => {
    expect(ctx.effortClass(8)).toBe('effort-hard')
    expect(ctx.effortClass(10)).toBe('effort-hard')
  })

  it('handles boundary values correctly', () => {
    expect(ctx.effortClass(0)).toBe('effort-easy')  // 0 <= 4
  })

  // [BUG] undefined coerces to NaN in comparisons; NaN <= 4 is false, so
  // undefined falls through all conditions and returns "effort-hard".
  // A missing effort value should probably return "effort-easy" or a neutral class.
  it('[BUG] undefined effort should not return effort-hard', () => {
    expect(ctx.effortClass(undefined)).not.toBe('effort-hard')
  })
})
