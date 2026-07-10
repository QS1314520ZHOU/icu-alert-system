/**
 * AudioCapture — manages AudioContext + AudioWorkletNode + parallel
 * MediaRecorder backup for voice rounding streaming.
 */

const TARGET_SAMPLE_RATE = 16000;
const MEDIA_RECORDER_TIMESLICE_MS = 5000; // 5 s backup chunks
const MAX_BACKUP_BYTES = 20 * 1024 * 1024; // 20 MB

export interface CaptureCallbacks {
  onPcmChunk: (pcm: ArrayBuffer) => void;
  onPcmFinal: (pcm: ArrayBuffer) => void;
  onError: (message: string) => void;
  onBackupExceeded?: () => void;
}

export class AudioCapture {
  private _context: AudioContext | null = null;
  private _stream: MediaStream | null = null;
  private _node: AudioWorkletNode | null = null;
  private _source: MediaStreamAudioSourceNode | null = null;
  private _mediaRecorder: MediaRecorder | null = null;
  private _backupChunks: Blob[] = [];
  private _backupExceeded = false;
  private _callbacks: CaptureCallbacks;
  private _sampleRate = TARGET_SAMPLE_RATE;

  constructor(callbacks: CaptureCallbacks) {
    this._callbacks = callbacks;
  }

  get sampleRate(): number {
    return this._sampleRate;
  }

  get backupExceeded(): boolean {
    return this._backupExceeded;
  }

  async start(): Promise<void> {
    // 1. Get microphone stream
    this._stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
      },
    });

    // 2. Create AudioContext at 16 kHz
    this._context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
    this._sampleRate = this._context.sampleRate;

    // 3. Load AudioWorklet module
    await this._context.audioWorklet.addModule('/audio/pcm-processor.js');

    // 4. Create node
    this._node = new AudioWorkletNode(this._context, 'pcm-processor');
    this._node.port.onmessage = (event: MessageEvent) => {
      const data = event.data as { pcm: ArrayBuffer; final?: boolean };
      if (!data || !data.pcm) return;
      if (data.final) {
        this._callbacks.onPcmFinal(data.pcm);
      } else {
        this._callbacks.onPcmChunk(data.pcm);
      }
    };

    this._node.onprocessorerror = () => {
      this._callbacks.onError('AudioWorklet 处理器异常');
    };

    // 5. Connect graph
    this._source = this._context.createMediaStreamSource(this._stream);
    this._source.connect(this._node);

    // 6. Start parallel MediaRecorder backup
    this._startBackupRecorder();
  }

  stop(): void {
    // Signal worklet to flush
    if (this._node) {
      this._node.port.postMessage({ type: 'stop' });
    }

    // Stop MediaRecorder
    if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
      this._mediaRecorder.stop();
    }

    // Release audio graph
    this._node?.disconnect();
    this._source?.disconnect();
    this._stream?.getTracks().forEach((t) => t.stop());
    this._context?.close();

    this._node = null;
    this._source = null;
    this._stream = null;
    this._context = null;
    this._mediaRecorder = null;
  }

  getBackupBlob(): Blob | null {
    if (this._backupChunks.length === 0) return null;
    return new Blob(this._backupChunks, { type: 'audio/webm;codecs=opus' });
  }

  clearBackup(): void {
    this._backupChunks = [];
    this._backupExceeded = false;
  }

  // ── Private ──────────────────────────────────────────────────────────

  private _startBackupRecorder(): void {
    if (!this._stream) return;
    try {
      this._mediaRecorder = new MediaRecorder(this._stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
    } catch {
      // Fallback — browser doesn't support the requested mimeType
      try {
        this._mediaRecorder = new MediaRecorder(this._stream);
      } catch {
        return; // no backup possible
      }
    }

    this._mediaRecorder.ondataavailable = (e: BlobEvent) => {
      if (!e.data || e.data.size === 0) return;
      const currentSize = this._backupChunks.reduce((s, c) => s + c.size, 0);
      if (currentSize + e.data.size > MAX_BACKUP_BYTES) {
        this._backupExceeded = true;
        this._callbacks.onBackupExceeded?.();
        return; // stop appending but keep existing chunks
      }
      this._backupChunks.push(e.data);
    };

    this._mediaRecorder.onerror = () => {
      this._callbacks.onError('备份录音异常');
    };

    this._mediaRecorder.start(MEDIA_RECORDER_TIMESLICE_MS);
  }
}
