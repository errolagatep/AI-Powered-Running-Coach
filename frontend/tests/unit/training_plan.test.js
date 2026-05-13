/**
 * Tests for pure functions in frontend/js/training_plan.js:
 *   parseTimeToMinutes, formatTargetTime, getLocalMondayISO,
 *   addDaysToDateKey, dateStrToLocalKey, badgeForType
 *
 * auth.js must be loaded first because training_plan.js calls escapeHtml, effortClass.
 * Bugs caught are marked [BUG].
 */

import { describe, it, expect, beforeAll } from 'vitest'
import { loadScript } from '../setup/loadScript.js'

let ctx

beforeAll(() => {
  ctx = loadScript('auth.js', 'training_plan.js')
})

// ── parseTimeToMinutes ───────────────────────────────────────────────────────

describe('parseTimeToMinutes', () => {
  describe('H:MM:SS format (3-part)', () => {
    it('parses 1:30:00 as 90 minutes', () => {
      expect(ctx.parseTimeToMinutes('1:30:00')).toBeCloseTo(90)
    })

    it('parses 3:45:30 as 225.5 minutes', () => {
      expect(ctx.parseTimeToMinutes('3:45:30')).toBeCloseTo(225.5)
    })

    it('parses 0:45:00 as 45 minutes', () => {
      expect(ctx.parseTimeToMinutes('0:45:00')).toBeCloseTo(45)
    })
  })

  describe('H:MM format (2-part, isPace=false) — first part 1-9 treated as hours', () => {
    it('parses "3:30" as 3h30m = 210 minutes', () => {
      expect(ctx.parseTimeToMinutes('3:30')).toBeCloseTo(210)
    })

    it('parses "1:45" as 1h45m = 105 minutes', () => {
      expect(ctx.parseTimeToMinutes('1:45')).toBeCloseTo(105)
    })

    it('parses "9:59" as 9h59m = 599 minutes (boundary: 9 is last H:MM value)', () => {
      expect(ctx.parseTimeToMinutes('9:59')).toBeCloseTo(599)
    })
  })

  describe('MM:SS format (2-part, isPace=false) — first part >= 10 treated as MM:SS', () => {
    it('parses "45:00" as 45 minutes', () => {
      expect(ctx.parseTimeToMinutes('45:00')).toBeCloseTo(45)
    })

    it('parses "10:30" as 10.5 minutes', () => {
      expect(ctx.parseTimeToMinutes('10:30')).toBeCloseTo(10.5)
    })

    it('parses "59:30" as 59.5 minutes', () => {
      expect(ctx.parseTimeToMinutes('59:30')).toBeCloseTo(59.5)
    })
  })

  describe('isPace=true — always MM:SS regardless of first part', () => {
    it('parses "5:30" as 5.5 min/km', () => {
      expect(ctx.parseTimeToMinutes('5:30', true)).toBeCloseTo(5.5)
    })

    it('parses "4:00" as 4 min/km', () => {
      expect(ctx.parseTimeToMinutes('4:00', true)).toBeCloseTo(4)
    })

    // First part <= 9 should still be treated as MM:SS when isPace=true
    it('parses "6:15" as 6.25 min/km (not 6h15m)', () => {
      expect(ctx.parseTimeToMinutes('6:15', true)).toBeCloseTo(6.25)
    })
  })

  describe('invalid input', () => {
    it('returns null for non-numeric input', () => {
      expect(ctx.parseTimeToMinutes('abc')).toBeNull()
      expect(ctx.parseTimeToMinutes('x:y')).toBeNull()
    })

    it('returns null for empty parts', () => {
      expect(ctx.parseTimeToMinutes('')).toBeNull()
    })

    it('returns null for single-part string', () => {
      expect(ctx.parseTimeToMinutes('45')).toBeNull()
    })
  })
})

// ── formatTargetTime ─────────────────────────────────────────────────────────

describe('formatTargetTime', () => {
  it('formats sub-hour times as "X min"', () => {
    expect(ctx.formatTargetTime(45)).toBe('45 min')
    expect(ctx.formatTargetTime(30)).toBe('30 min')
  })

  it('formats exactly 0 minutes', () => {
    expect(ctx.formatTargetTime(0)).toBe('0 min')
  })

  it('formats whole-hour times', () => {
    expect(ctx.formatTargetTime(60)).toBe('1h 0m')
    expect(ctx.formatTargetTime(120)).toBe('2h 0m')
  })

  it('formats hours and minutes', () => {
    expect(ctx.formatTargetTime(90)).toBe('1h 30m')
    expect(ctx.formatTargetTime(225)).toBe('3h 45m')
  })

  // [BUG] When minutes rounds up to 60, the h/m split is wrong.
  // formatTargetTime(119.9) → h=1, m=round(59.9)=60 → "1h 60m" not "2h 0m"
  it('[BUG] handles fractional minutes that round up to 60 (carry-over)', () => {
    expect(ctx.formatTargetTime(119.9)).toBe('2h 0m')  // currently "1h 60m"
    expect(ctx.formatTargetTime(59.9)).toBe('1h 0m')   // currently "60 min"
  })
})

// ── getLocalMondayISO ─────────────────────────────────────────────────────────

describe('getLocalMondayISO', () => {
  it('returns a string in YYYY-MM-DD format', () => {
    const result = ctx.getLocalMondayISO()
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('returns the Monday of the current week', () => {
    const result = ctx.getLocalMondayISO()
    const [y, m, d] = result.split('-').map(Number)
    const monday = new Date(y, m - 1, d)
    // getDay() returns 1 for Monday
    expect(monday.getDay()).toBe(1)
  })

  it('result is <= today', () => {
    const result = ctx.getLocalMondayISO()
    const today = new Date()
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    expect(result <= todayStr).toBe(true)
  })
})

// ── dateStrToLocalKey ─────────────────────────────────────────────────────────

describe('dateStrToLocalKey', () => {
  it('returns only the YYYY-MM-DD portion', () => {
    expect(ctx.dateStrToLocalKey('2025-06-15T10:30:00')).toBe('2025-06-15')
    expect(ctx.dateStrToLocalKey('2025-06-15')).toBe('2025-06-15')
  })

  it('truncates UTC suffix', () => {
    expect(ctx.dateStrToLocalKey('2025-01-01T00:00:00Z')).toBe('2025-01-01')
  })
})

// ── addDaysToDateKey ──────────────────────────────────────────────────────────

describe('addDaysToDateKey', () => {
  it('adds days within the same month', () => {
    expect(ctx.addDaysToDateKey('2025-06-10', 5)).toBe('2025-06-15')
  })

  it('handles month boundary correctly', () => {
    expect(ctx.addDaysToDateKey('2025-01-29', 3)).toBe('2025-02-01')
    expect(ctx.addDaysToDateKey('2025-12-30', 2)).toBe('2026-01-01')
  })

  it('handles subtracting days', () => {
    expect(ctx.addDaysToDateKey('2025-06-03', -3)).toBe('2025-05-31')
    expect(ctx.addDaysToDateKey('2025-03-01', -1)).toBe('2025-02-28')
  })

  it('adds 0 days returns same key', () => {
    expect(ctx.addDaysToDateKey('2025-07-04', 0)).toBe('2025-07-04')
  })

  it('handles leap year correctly', () => {
    // 2024 is a leap year
    expect(ctx.addDaysToDateKey('2024-02-28', 1)).toBe('2024-02-29')
    expect(ctx.addDaysToDateKey('2024-02-29', 1)).toBe('2024-03-01')
  })

  it('pads single-digit months and days', () => {
    expect(ctx.addDaysToDateKey('2025-01-01', 0)).toBe('2025-01-01')
    expect(ctx.addDaysToDateKey('2025-10-31', 1)).toBe('2025-11-01')
  })
})

// ── badgeForType ──────────────────────────────────────────────────────────────

describe('badgeForType', () => {
  it('maps easy run types', () => {
    expect(ctx.badgeForType('Easy Run')).toBe('badge-easy')
    expect(ctx.badgeForType('easy')).toBe('badge-easy')
  })

  it('maps tempo run types', () => {
    expect(ctx.badgeForType('Tempo Run')).toBe('badge-tempo')
    expect(ctx.badgeForType('tempo')).toBe('badge-tempo')
  })

  it('maps interval types', () => {
    expect(ctx.badgeForType('Interval Training')).toBe('badge-interval')
  })

  it('maps long run types', () => {
    expect(ctx.badgeForType('Long Run')).toBe('badge-long')
  })

  it('maps cross training', () => {
    expect(ctx.badgeForType('Cross Training')).toBe('badge-cross')
  })

  it('maps active recovery', () => {
    expect(ctx.badgeForType('Active Recovery')).toBe('badge-recovery')
  })

  it('maps rest days', () => {
    expect(ctx.badgeForType('Rest')).toBe('badge-rest')
    expect(ctx.badgeForType('Rest Day')).toBe('badge-rest')
  })

  it('defaults to badge-easy for unknown type', () => {
    expect(ctx.badgeForType('Unknown')).toBe('badge-easy')
  })

  // Case insensitivity
  it('is case-insensitive', () => {
    expect(ctx.badgeForType('TEMPO')).toBe('badge-tempo')
    expect(ctx.badgeForType('Long RUN')).toBe('badge-long')
  })
})
