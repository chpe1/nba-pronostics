import { describe, it, expect } from 'vitest'
import { computeGaugeOffset } from './gauge'

describe('computeGaugeOffset', () => {
  it('returns the centre (0) for a null gap', () => {
    expect(computeGaugeOffset(0, 30)).toBe(0)
  })

  it('reaches the maximum deport (1) when the gap equals the high threshold', () => {
    expect(computeGaugeOffset(30, 30)).toBe(1)
  })

  it('clips beyond the high threshold, never exceeding the maximum deport', () => {
    expect(computeGaugeOffset(58, 30)).toBe(1)
    expect(computeGaugeOffset(1000, 30)).toBe(1)
  })

  it('deports to the other side for a negative gap', () => {
    expect(computeGaugeOffset(-15, 30)).toBe(-0.5)
    expect(computeGaugeOffset(-30, 30)).toBe(-1)
    expect(computeGaugeOffset(-1000, 30)).toBe(-1)
  })
})
