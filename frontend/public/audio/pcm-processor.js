/**
 * PCM Processor — AudioWorkletProcessor for voice rounding.
 *
 * Converts Float32 microphone input to Int16 PCM chunks (mono, target 16 kHz).
 *
 * ⚠️  If the AudioContext was created with {sampleRate: 16000}, no resampling
 * is needed — only Float32→Int16 conversion.  The inline resampler below is
 * a FALLBACK for browsers that don't honour the requested sampleRate.
 *
 * Mirrors: frontend/src/audio/resampler.ts  (keep in sync manually or via build)
 */

const TARGET_SAMPLE_RATE = 16000;
const CHUNK_DURATION_MS = 60; // 60 ms per chunk — matches FunASR stride
const CHUNK_SAMPLES = Math.floor(TARGET_SAMPLE_RATE * CHUNK_DURATION_MS / 1000); // 960

// ── Inline resampler (mirrors resampler.ts) ───────────────────────────────

class Resampler {
  constructor(inputRate, outputRate) {
    this.ratio = inputRate / outputRate;
    this.frac = 0;
  }

  /** @param {Float32Array} input @returns {Float32Array} */
  process(input) {
    const outLen = Math.floor((input.length - this.frac) / this.ratio);
    const output = new Float32Array(Math.max(0, outLen));
    let outIdx = 0;
    let pos = this.frac;
    while (pos < input.length && outIdx < outLen) {
      const idx = Math.floor(pos);
      const f = pos - idx;
      const a = input[idx];
      const b = idx + 1 < input.length ? input[idx + 1] : a;
      output[outIdx++] = a + f * (b - a);
      pos += this.ratio;
    }
    this.frac = Math.max(0, pos - input.length);
    return output;
  }
}

// ── Float32 → Int16 converter ────────────────────────────────────────────

/**
 * Convert Float32 samples (-1..1) to Int16 little-endian ArrayBuffer.
 * @param {Float32Array} samples
 * @returns {ArrayBuffer}
 */
function float32ToInt16(samples) {
  const buf = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    const val = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7FFF);
    view.setInt16(i * 2, val, true); // little-endian
  }
  return buf;
}

// ── Processor ─────────────────────────────────────────────────────────────

class PcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    /** @type {Float32Array[]} */
    this._buffer = [];
    this._resampler = null; // created lazily when rate differs
    this._stopped = false;

    this.port.onmessage = (event) => {
      if (event.data && event.data.type === 'stop') {
        this._flush();
        this._stopped = true;
      }
    };
  }

  /**
   * @param {Float32Array[][]} inputs
   * @param {Float32Array[][]} outputs
   * @param {Record<string, Float32Array>} parameters
   * @returns {boolean}
   */
  process(inputs, outputs, parameters) {
    if (this._stopped) return false;

    const input = inputs[0] && inputs[0][0];
    if (!input || input.length === 0) return true;

    const inputSampleRate = sampleRate; // inherited from AudioContext

    let samples;
    if (inputSampleRate === TARGET_SAMPLE_RATE) {
      samples = input;
    } else {
      // Resampling needed
      if (!this._resampler) {
        this._resampler = new Resampler(inputSampleRate, TARGET_SAMPLE_RATE);
      }
      samples = this._resampler.process(input);
    }

    if (samples.length > 0) {
      this._accumulate(samples);
    }

    return true; // keep the processor alive
  }

  /** @param {Float32Array} samples */
  _accumulate(samples) {
    this._buffer.push(samples);

    let total = this._buffer.reduce((sum, arr) => sum + arr.length, 0);
    while (total >= CHUNK_SAMPLES) {
      const chunk = new Float32Array(CHUNK_SAMPLES);
      let offset = 0;
      while (offset < CHUNK_SAMPLES) {
        const buf = this._buffer[0];
        const needed = CHUNK_SAMPLES - offset;
        if (buf.length <= needed) {
          chunk.set(buf, offset);
          offset += buf.length;
          this._buffer.shift();
        } else {
          chunk.set(buf.subarray(0, needed), offset);
          this._buffer[0] = buf.subarray(needed);
          offset += needed;
        }
      }
      total -= CHUNK_SAMPLES;

      const pcm = float32ToInt16(chunk);
      // Transfer ownership of the buffer to the main thread (zero-copy)
      this.port.postMessage({ pcm }, [pcm]);
    }
  }

  _flush() {
    while (this._buffer.length > 0) {
      const total = this._buffer.reduce((sum, arr) => sum + arr.length, 0);
      if (total === 0) break;
      const chunk = new Float32Array(total);
      let offset = 0;
      for (const buf of this._buffer) {
        chunk.set(buf, offset);
        offset += buf.length;
      }
      this._buffer = [];
      const pcm = float32ToInt16(chunk);
      this.port.postMessage({ pcm, final: true }, [pcm]);
    }
  }
}

registerProcessor('pcm-processor', PcmProcessor);
