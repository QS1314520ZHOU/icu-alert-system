/**
 * VoiceRoundingSession — per-session WebSocket client for 2pass streaming.
 *
 * NOT a global singleton.  Each recording creates a new instance.
 * Lifecycle: connect → start → send PCM → stop → receive completed draft.
 */

import type { VoiceRoundingDraft } from '../api/voiceRounding';

// ── Message types ────────────────────────────────────────────────────────

export interface ConnectedMessage {
  type: 'connected';
  session_id: string;
}

export interface ReadyMessage {
  type: 'ready';
  session_id: string;
  sample_rate: number;
}

export interface PartialMessage {
  type: 'partial';
  text: string;
  start_ms: number | null;
  end_ms: number | null;
}

export interface FinalSegmentMessage {
  type: 'final_segment';
  text: string;
  start_ms: number | null;
  end_ms: number | null;
  segments: Array<Record<string, unknown>>;
}

export interface StoppedMessage {
  type: 'stopped';
}

export interface CompletedMessage {
  type: 'completed';
  draft: VoiceRoundingDraft;
}

export interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
  degraded?: boolean;
  partial_text?: string;
  committed_text?: string;
}

export interface PongMessage {
  type: 'pong';
}

export interface BackpressureWarningMessage {
  type: 'backpressure_warning';
  dropped_chunks: number;
}

export type VoiceRoundingStreamMessage =
  | ConnectedMessage
  | ReadyMessage
  | PartialMessage
  | FinalSegmentMessage
  | StoppedMessage
  | CompletedMessage
  | ErrorMessage
  | PongMessage
  | BackpressureWarningMessage;

// ── Session state ────────────────────────────────────────────────────────

export type SessionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'ready'
  | 'recording'
  | 'stopping'
  | 'completed'
  | 'error';

// ── Backpressure config ──────────────────────────────────────────────────

const MAX_BUFFERED_BYTES = 1920 * 32; // 32 chunks ≈ 1.92 s
const MAX_CONSECUTIVE_DROPS = 30;

// ── Session class ────────────────────────────────────────────────────────

export type MessageListener = (msg: VoiceRoundingStreamMessage) => void;

export class VoiceRoundingSession {
  private _ws: WebSocket | null = null;
  private _state: SessionState = 'idle';
  private _patientId: string;
  private _listeners = new Set<MessageListener>();
  private _droppedChunks = 0;
  private _sessionId = '';

  constructor(patientId: string) {
    this._patientId = patientId;
  }

  get state(): SessionState {
    return this._state;
  }

  get sessionId(): string {
    return this._sessionId;
  }

  // ── Public API ──────────────────────────────────────────────────────

  onMessage(listener: MessageListener): () => void {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  connect(wsUrl: string): void {
    if (this._ws) return;
    this._state = 'connecting';
    this._ws = new WebSocket(wsUrl);

    this._ws.onopen = () => {
      // connected message will be sent by backend after auth
    };

    this._ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data) as VoiceRoundingStreamMessage;
          this._handleMessage(msg);
        } catch {
          // ignore parse errors
        }
      }
    };

    this._ws.onclose = () => {
      if (this._state !== 'completed' && this._state !== 'error') {
        this._dispatch({
          type: 'error',
          code: 'ws_closed',
          message: 'WebSocket 连接已关闭',
        });
      }
      this._state = 'error';
      this._ws = null;
    };

    this._ws.onerror = () => {
      // onclose will fire after this
    };
  }

  sendStart(): void {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
    this._ws.send(
      JSON.stringify({
        type: 'start',
        patient_id: this._patientId,
        sample_rate: 16000,
        channels: 1,
      }),
    );
  }

  sendPcmChunk(pcm: ArrayBuffer): void {
    if (this._state !== 'ready' && this._state !== 'recording') return;
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;

    if (this._state === 'ready') {
      this._state = 'recording';
    }

    if (this._ws.bufferedAmount <= MAX_BUFFERED_BYTES) {
      this._ws.send(pcm);
      this._droppedChunks = 0;
    } else {
      this._droppedChunks++;
      if (this._droppedChunks >= MAX_CONSECUTIVE_DROPS) {
        this._dispatch({
          type: 'error',
          code: 'backpressure',
          message: `连续丢帧 ${this._droppedChunks} 次，网络拥塞`,
        });
        this._state = 'error';
      }
    }
  }

  sendStop(): void {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) return;
    this._state = 'stopping';
    this._ws.send(JSON.stringify({ type: 'stop' }));
  }

  sendCancel(): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'cancel' }));
    }
    this._cleanup();
  }

  sendPing(): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: 'ping' }));
    }
  }

  close(): void {
    this._cleanup();
  }

  // ── Private ──────────────────────────────────────────────────────────

  private _handleMessage(msg: VoiceRoundingStreamMessage): void {
    switch (msg.type) {
      case 'connected':
        this._state = 'connected';
        this._sessionId = msg.session_id;
        // Auto-send start after connected
        this.sendStart();
        break;
      case 'ready':
        this._state = 'ready';
        break;
      case 'partial':
        // no state change
        break;
      case 'final_segment':
        // no state change
        break;
      case 'stopped':
        // staying in stopping
        break;
      case 'completed':
        this._state = 'completed';
        break;
      case 'error':
        this._state = 'error';
        break;
    }
    this._dispatch(msg);
  }

  private _dispatch(msg: VoiceRoundingStreamMessage): void {
    for (const listener of this._listeners) {
      try {
        listener(msg);
      } catch {
        // don't let one bad listener break others
      }
    }
  }

  private _cleanup(): void {
    this._state = 'idle';
    if (this._ws) {
      this._ws.onclose = null;
      this._ws.onerror = null;
      this._ws.onmessage = null;
      if (this._ws.readyState === WebSocket.OPEN) {
        this._ws.close();
      }
      this._ws = null;
    }
    this._listeners.clear();
    this._droppedChunks = 0;
  }
}

// ── URL builder ──────────────────────────────────────────────────────────

export function buildVoiceRoundingWsUrl(patientId: string): string {
  const wsBase = (import.meta.env.VITE_WS_BASE_URL as string | undefined) || '';
  if (wsBase) {
    return `${wsBase.replace(/\/$/, '')}/api/voice-rounding/ws/voice-rounding/${patientId}`;
  }
  const { protocol, host } = window.location;
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProto}//${host}/api/voice-rounding/ws/voice-rounding/${patientId}`;
}
