"""ASR 客户端：SenseVoice / FunASR 封装。本地部署，音频不出院。"""
from __future__ import annotations

import json
import logging
from typing import Any

import websockets  # websockets==14.1 (requirements.common.txt)

logger = logging.getLogger("icu-alert")


class ASRClient:
    """
    FunASR 官方 WebSocket 协议客户端。

    对接点：FunASR runtime 的 WS 协议字段（chunk_size/mode/hotwords）
    请按实际部署的 funasr runtime 版本核对：
    https://github.com/modelscope/FunASR/blob/main/runtime/docs/

    若用 SenseVoice ONNX 直接 import，把 mode 改成 local_import 并实现 _transcribe_local。
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg or {}
        self.mode = str(self.cfg.get("mode", "funasr_ws"))
        self.ws_url = str(self.cfg.get("ws_url", "ws://127.0.0.1:10095"))
        self.model = str(self.cfg.get("model", "sensevoice"))
        self.hotwords = self._load_hotwords(self.cfg.get("hotword_path"))

    def _load_hotwords(self, path: str | None) -> str:
        """加载热词文件。FunASR 热词格式：每行 '词 权重'，如 '去甲肾上腺素 20'。"""
        if not path:
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            logger.warning("hotword 文件读取失败: %s", path)
            return ""

    async def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000) -> str:
        if self.mode == "funasr_ws":
            return await self._transcribe_funasr_ws(audio_bytes, sample_rate)
        if self.mode == "local_import":
            return await self._transcribe_local(audio_bytes, sample_rate)
        if self.mode == "mock":
            return await self._transcribe_mock(audio_bytes, sample_rate)
        raise ValueError(f"未知 ASR mode: {self.mode}")

    async def _transcribe_mock(self, audio_bytes: bytes, sample_rate: int) -> str:
        """Mock 模式：跳过 ASR，返回测试文本。用于无 ASR 环境时测试后续流水线。"""
        logger.info("ASR mock 模式：返回测试文本（音频 %d 字节）", len(audio_bytes))
        return "患者今天嗯血压稳定哦，体温三八点五度，心率一百二十次每分，嗯用了去甲肾上腺素零点二微克每公斤每分钟"

    async def _transcribe_funasr_ws(self, audio_bytes: bytes, sample_rate: int) -> str:
        """
        FunASR offline WebSocket 协议。

        ⚠️ 字段以部署的 runtime 为准。参考：
        https://github.com/modelscope/FunASR/blob/main/runtime/readme_cn.md
        """
        result_text = ""
        async with websockets.connect(self.ws_url, ping_interval=None) as ws:
            # 1) 发送配置帧（含热词）
            config = {
                "mode": "offline",
                "chunk_size": [5, 10, 5],
                "wav_name": "rounding",
                "is_speaking": True,
                "hotwords": self.hotwords,
                "itn": True,  # 逆文本规整：三十八度五 → 38.5
            }
            await ws.send(json.dumps(config))
            # 2) 发送音频（PCM 16k 16bit mono；若浏览器传来 webm/opus 需先转码，见 service 层）
            await ws.send(audio_bytes)
            # 3) 发送结束帧
            await ws.send(json.dumps({"is_speaking": False}))
            # 4) 收结果
            async for message in ws:
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                if "text" in data:
                    result_text += str(data.get("text") or "")
                # offline 模式下 is_final 或 mode 字段标识结束
                if data.get("is_final") or data.get("mode") == "offline":
                    break
        return result_text.strip()

    async def _transcribe_local(self, audio_bytes: bytes, sample_rate: int) -> str:
        """
        可选：直接 import SenseVoice/FunASR 模型推理（不走 WS）。

        from funasr import AutoModel
        self._model = AutoModel(model="iic/SenseVoiceSmall", ...)
        res = self._model.generate(input=<wav路径或array>, hotword=self.hotwords)
        return res[0]["text"]

        建议放独立进程/容器，避免阻塞 FastAPI 事件循环（用 run_in_executor）。
        """
        raise NotImplementedError("local_import 模式请按部署实现")
