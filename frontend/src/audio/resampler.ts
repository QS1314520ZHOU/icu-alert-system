/**
 * Stateful resampler — converts arbitrary sample rates to a target rate.
 *
 * Used by both the AudioWorkletProcessor (via bundled build) and unit tests.
 *
 * 【MVP limitation】Uses linear interpolation without anti-aliasing low-pass
 * filter.  High-frequency content (>8 kHz) may alias.  Acceptable for speech
 * recognition (energy concentrated below 4 kHz).  Not suitable for music or
 * precision spectral analysis.
 *
 * Usage:
 *   import { createResampler, resample } from './resampler';
 *   const state = createResampler(inputRate, 16000);
 *   const output = resample(state, inputFloat32Array);
 *   // state.frac preserves phase across process() calls.
 */

export interface ResamplerState {
  inputRate: number;
  outputRate: number;
  /** Accumulated fractional position carried across calls. */
  frac: number;
}

export function createResampler(
  inputRate: number,
  outputRate: number,
): ResamplerState {
  return { inputRate, outputRate, frac: 0 };
}

export function resample(
  state: ResamplerState,
  input: Float32Array,
): Float32Array {
  const ratio = state.inputRate / state.outputRate;
  const outLen = Math.floor((input.length - state.frac) / ratio);
  const output = new Float32Array(Math.max(0, outLen));
  let outIdx = 0;
  let pos = state.frac;

  while (pos < input.length && outIdx < outLen) {
    const idx = Math.floor(pos);
    const f = pos - idx;
    const a = input[idx];
    const b = idx + 1 < input.length ? input[idx + 1] : a;
    output[outIdx++] = a + f * (b - a);
    pos += ratio;
  }

  state.frac = Math.max(0, pos - input.length);
  return output;
}
