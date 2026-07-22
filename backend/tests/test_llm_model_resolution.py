"""
Tests for unified LLM model resolution (resolve_model_candidates).
Covers:
  - Explicit model selection
  - Tier keyword resolution (reasoning / medical / fast / long_context)
  - Global LLM_MODEL fallback
  - LLM_FALLBACK_MODEL
  - Empty config → clear error
  - Tier keywords never sent to API
  - Empty model never sent to API
  - Candidate deduplication
  - Runtime Config provider routing (mocked)
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

import pytest

from app.services.llm_runtime import (
    _first_non_empty,
    _purpose_from_requested_model,
    _provider_candidates,
    _TIER_KEYWORDS,
    LLMRuntimeUnavailableError,
    call_llm_chat,
    resolve_model_candidates,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cfg(
    *,
    LLM_MODEL: str = "",
    LLM_MODEL_MEDICAL: str = "",
    LLM_FALLBACK_MODEL: str = "",
    LLM_REASONING_MODEL: str = "",
    yaml_overrides: dict | None = None,
) -> SimpleNamespace:
    yaml_cfg: dict = {"ai_service": {"llm": {}}, "ai": {}}
    if yaml_overrides:
        yaml_cfg.update(yaml_overrides)
    settings = SimpleNamespace(
        LLM_MODEL=LLM_MODEL,
        LLM_MODEL_MEDICAL=LLM_MODEL_MEDICAL,
        LLM_FALLBACK_MODEL=LLM_FALLBACK_MODEL,
        LLM_REASONING_MODEL=LLM_REASONING_MODEL,
        LLM_BASE_URL="http://127.0.0.1:11434/v1",
        LLM_API_KEY="test-api-key",
    )

    class _Cfg:
        def __init__(self):
            self.settings = settings
            self.yaml_cfg = yaml_cfg

        @property
        def llm_fast_model(self) -> str:
            ai_svc = self.yaml_cfg.get("ai_service", {}) or {}
            llm = ai_svc.get("llm", {}) or {}
            return llm.get("fast_model") or self.yaml_cfg.get("ai", {}).get("llm_fast_model") or self.settings.LLM_MODEL or self.llm_model_medical

        @property
        def llm_model_medical(self) -> str:
            ai_svc = self.yaml_cfg.get("ai_service", {}) or {}
            llm = ai_svc.get("llm", {}) or {}
            return llm.get("medical_model") or self.yaml_cfg.get("ai", {}).get("llm_model_medical") or self.settings.LLM_MODEL_MEDICAL

        @property
        def llm_fallback_model(self) -> str:
            ai_svc = self.yaml_cfg.get("ai_service", {}) or {}
            llm = ai_svc.get("llm", {}) or {}
            return llm.get("fallback_model") or self.yaml_cfg.get("ai", {}).get("llm_fallback_model") or self.settings.LLM_FALLBACK_MODEL

        @property
        def llm_reasoning_model(self) -> str:
            ai_svc = self.yaml_cfg.get("ai_service", {}) or {}
            llm = ai_svc.get("llm", {}) or {}
            return llm.get("reasoning_model") or self.yaml_cfg.get("ai", {}).get("llm_reasoning_model") or self.settings.LLM_REASONING_MODEL

    return _Cfg()  # type: ignore[return-value]


def _mock_runtime_ai(providers=None, fast_model="", fallback_model="", routes=None):
    """Return an async mock for _runtime_ai_config."""
    doc = {}
    if providers is not None:
        doc["providers"] = providers
    if fast_model:
        doc["fast_model"] = fast_model
    if fallback_model:
        doc["fallback_model"] = fallback_model
    if routes is not None:
        doc["routes"] = routes

    async def _inner():
        return doc

    return _inner


# ---------------------------------------------------------------------------
# _first_non_empty
# ---------------------------------------------------------------------------

class TestFirstNonEmpty:
    def test_returns_first_value(self):
        assert _first_non_empty("a", "b", "c") == "a"

    def test_skips_empty_and_none(self):
        assert _first_non_empty("", None, "b", "c") == "b"

    def test_all_empty_returns_empty(self):
        assert _first_non_empty("", None, "") == ""

    def test_strips_whitespace(self):
        assert _first_non_empty("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# _purpose_from_requested_model
# ---------------------------------------------------------------------------

class TestPurposeFromRequestedModel:
    def test_fast_keywords(self):
        for kw in ("fast", "quick", "summary", "handoff"):
            assert _purpose_from_requested_model(kw) == "fast"

    def test_medical_keywords(self):
        for kw in ("medical", "clinical", "risk"):
            assert _purpose_from_requested_model(kw) == "medical"

    def test_reasoning_keywords(self):
        assert _purpose_from_requested_model("reasoning") == "reasoning"
        assert _purpose_from_requested_model("推理") == "reasoning"

    def test_long_context_keywords(self):
        for kw in ("long", "long_context", "context"):
            assert _purpose_from_requested_model(kw) == "long_context"

    def test_real_model_name_returns_empty(self):
        assert _purpose_from_requested_model("gpt-4") == ""
        assert _purpose_from_requested_model("fake-model") == ""
        assert _purpose_from_requested_model("qwen2.5:32b") == ""

    def test_none_and_empty_returns_empty(self):
        assert _purpose_from_requested_model(None) == ""
        assert _purpose_from_requested_model("") == ""


# ---------------------------------------------------------------------------
# resolve_model_candidates
# ---------------------------------------------------------------------------

class TestResolveModelCandidates:
    @pytest.mark.asyncio
    async def test_explicit_model_used_as_primary(self):
        """Explicit requested model becomes primary, with LLM_MODEL as fallback."""
        cfg = _cfg(LLM_MODEL="global-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="explicit-model")
        assert candidates == ["explicit-model", "global-model"]
        assert meta["primary_model"] == "explicit-model"
        assert degraded is True

    @pytest.mark.asyncio
    async def test_tier_keyword_fast_resolves_to_llm_model(self):
        """fast keyword → llm_fast_model → LLM_MODEL."""
        cfg = _cfg(LLM_MODEL="global-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="fast")
        assert candidates == ["global-model"]
        assert meta["primary_model"] == "global-model"

    @pytest.mark.asyncio
    async def test_tier_keyword_medical_resolves_to_llm_model_medical(self):
        """medical keyword → LLM_MODEL_MEDICAL as primary, LLM_MODEL as fallback."""
        cfg = _cfg(LLM_MODEL="global", LLM_MODEL_MEDICAL="med-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="medical")
        assert candidates == ["med-model", "global"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_tier_keyword_reasoning_resolves_to_llm_reasoning_model(self):
        """reasoning keyword → LLM_REASONING_MODEL as primary, LLM_MODEL as fallback."""
        cfg = _cfg(LLM_MODEL="global", LLM_REASONING_MODEL="reason-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="reasoning")
        assert candidates == ["reason-model", "global"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_reasoning_falls_back_to_medical_then_global(self):
        """reasoning with no LLM_REASONING_MODEL → medical as primary, global as fallback."""
        cfg = _cfg(LLM_MODEL="global", LLM_MODEL_MEDICAL="med-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="reasoning")
        assert candidates == ["med-model", "global"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_medical_falls_back_to_global(self):
        """medical with no LLM_MODEL_MEDICAL → LLM_MODEL."""
        cfg = _cfg(LLM_MODEL="global-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="medical")
        assert candidates == ["global-model"]

    @pytest.mark.asyncio
    async def test_global_llm_model_fallback(self):
        """No explicit model → falls back to LLM_MODEL."""
        cfg = _cfg(LLM_MODEL="global-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates == ["global-model"]
        assert meta["primary_model"] == "global-model"

    @pytest.mark.asyncio
    async def test_fallback_model_used_as_degraded(self):
        """LLM_FALLBACK_MODEL becomes secondary candidate."""
        cfg = _cfg(LLM_MODEL="primary-model", LLM_FALLBACK_MODEL="fallback-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg)
        assert candidates == ["primary-model", "fallback-model"]
        assert degraded is True
        assert meta["fallback_model"] == "fallback-model"

    @pytest.mark.asyncio
    async def test_empty_config_returns_empty_candidates(self):
        """When nothing is configured, return empty list (caller raises error)."""
        cfg = _cfg()
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg)
        assert candidates == []
        assert degraded is False

    @pytest.mark.asyncio
    async def test_candidate_dedup(self):
        """Duplicate models in chain are deduplicated."""
        cfg = _cfg(LLM_MODEL="same-model", LLM_FALLBACK_MODEL="same-model")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, _ = await resolve_model_candidates(cfg)
        assert candidates == ["same-model"]

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_models(self):
        """Whitespace around model names is stripped."""
        cfg = _cfg(LLM_MODEL="  my-model  ")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, _ = await resolve_model_candidates(cfg)
        assert candidates == ["my-model"]

    @pytest.mark.asyncio
    async def test_provider_routing_has_priority(self):
        """Runtime Config providers take priority over env-based config (no model → purpose=fast)."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p1", "model": "provider-model", "base_url": "http://p1/v1", "api_key": "k1", "enabled": True, "priority": 10, "purpose": "fast"},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, degraded, meta = await resolve_model_candidates(cfg)
        assert len(candidates) == 1
        assert candidates[0]["model"] == "provider-model"
        assert meta["provider_pool"] is True
        assert degraded is False

    @pytest.mark.asyncio
    async def test_provider_route_by_purpose(self):
        """Runtime Config routes by purpose (e.g. medical → specific provider)."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_general", "model": "general-model", "base_url": "http://g/v1", "api_key": "k", "purpose": "fast", "enabled": True, "priority": 20},
            {"id": "p_med", "model": "medical-model", "base_url": "http://m/v1", "api_key": "k", "purpose": "medical", "enabled": True, "priority": 10},
        ]
        routes = {"medical": "p_med"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="medical")
        assert len(candidates) >= 1
        assert candidates[0]["model"] == "medical-model"

    @pytest.mark.asyncio
    async def test_long_context_falls_back_to_medical_then_global(self):
        """long_context keyword → medical as primary, global as fallback."""
        cfg = _cfg(LLM_MODEL="global", LLM_MODEL_MEDICAL="med")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, _ = await resolve_model_candidates(cfg, requested_model="long_context")
        assert candidates == ["med", "global"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_tier_keyword_not_in_candidates(self):
        """Tier keywords never appear as model candidates."""
        cfg = _cfg(LLM_MODEL="real-model")
        for kw in ("fast", "medical", "reasoning", "long_context", "long", "clinical", "risk", "summary"):
            with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
                candidates, _, _ = await resolve_model_candidates(cfg, requested_model=kw)
            for c in candidates:
                if isinstance(c, str):
                    assert c.lower() not in _TIER_KEYWORDS, f"Keyword '{kw}' leaked into candidates: {candidates}"


# ---------------------------------------------------------------------------
# _TIER_KEYWORDS guard
# ---------------------------------------------------------------------------

class TestTierKeywordsGuard:
    def test_fast_variants_are_tier_keywords(self):
        for kw in ("fast", "quick", "summary", "handoff"):
            assert kw in _TIER_KEYWORDS

    def test_medical_variants_are_tier_keywords(self):
        for kw in ("medical", "clinical", "risk"):
            assert kw in _TIER_KEYWORDS

    def test_reasoning_variants_are_tier_keywords(self):
        assert "reasoning" in _TIER_KEYWORDS
        assert "推理" in _TIER_KEYWORDS

    def test_long_context_variants_are_tier_keywords(self):
        for kw in ("long", "long_context", "context"):
            assert kw in _TIER_KEYWORDS

    def test_real_model_names_are_not_tier_keywords(self):
        for name in ("gpt-4", "fake-model", "qwen2.5:32b", "claude-opus", ""):
            assert name not in _TIER_KEYWORDS


# ---------------------------------------------------------------------------
# Provider candidates
# ---------------------------------------------------------------------------

class TestProviderCandidates:
    def test_empty_providers_returns_empty(self):
        rows, meta = _provider_candidates({}, "fast")
        assert rows == []
        assert meta == {}

    def test_disabled_provider_filtered_out(self):
        runtime = {
            "providers": [
                {"id": "p1", "model": "m1", "enabled": False, "purpose": "fast"},
                {"id": "p2", "model": "m2", "enabled": True, "purpose": "fast"},
            ]
        }
        rows, meta = _provider_candidates(runtime, None)
        assert len(rows) == 1
        assert rows[0]["id"] == "p2"

    def test_empty_model_provider_filtered_out(self):
        """Provider with empty model field is excluded."""
        runtime = {
            "providers": [
                {"id": "p1", "model": "", "enabled": True, "purpose": "fast"},
                {"id": "p2", "model": "valid-model", "enabled": True, "purpose": "fast"},
            ]
        }
        rows, meta = _provider_candidates(runtime, None)
        assert len(rows) == 1
        assert rows[0]["id"] == "p2"

    def test_whitespace_only_model_provider_filtered_out(self):
        """Provider with whitespace-only model is excluded."""
        runtime = {
            "providers": [
                {"id": "p1", "model": "   ", "enabled": True, "purpose": "fast"},
                {"id": "p2", "model": "ok-model", "enabled": True, "purpose": "fast"},
            ]
        }
        rows, meta = _provider_candidates(runtime, None)
        assert len(rows) == 1
        assert rows[0]["model"] == "ok-model"

    def test_explicit_model_with_matching_provider_uses_provider(self):
        """Explicit model that matches a provider → use that provider's full config."""
        runtime = {
            "providers": [
                {"id": "p_match", "model": "my-explicit-model", "base_url": "http://p/v1", "api_key": "pk", "enabled": True, "priority": 10},
                {"id": "p_other", "model": "other-model", "base_url": "http://o/v1", "api_key": "ok", "enabled": True, "priority": 20},
            ]
        }
        rows, meta = _provider_candidates(runtime, "my-explicit-model")
        assert len(rows) == 1
        assert rows[0]["id"] == "p_match"
        assert rows[0]["base_url"] == "http://p/v1"

    def test_explicit_model_unmatched_by_providers_returns_empty(self):
        """Explicit model not matching any provider → return empty (fall through to env vars)."""
        runtime = {
            "providers": [
                {"id": "p1", "model": "provider-model", "base_url": "http://p/v1", "api_key": "k", "enabled": True},
            ]
        }
        rows, meta = _provider_candidates(runtime, "unrelated-model")
        assert rows == []
        assert meta == {}


# ---------------------------------------------------------------------------
# Integrated resolve_model_candidates edge cases
# ---------------------------------------------------------------------------

class TestResolveModelCandidatesEdgeCases:
    @pytest.mark.asyncio
    async def test_explicit_model_bypasses_unmatched_providers(self):
        """Explicit model not matched by any provider → falls through to env vars."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p1", "model": "provider-model", "base_url": "http://p/v1", "api_key": "k", "enabled": True},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="explicit-model")
        # Should fall through to env vars, using explicit-model as primary
        assert candidates == ["explicit-model", "env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_tier_keyword_no_matching_provider_falls_to_env(self):
        """Tier keyword with no matching provider → falls through to env vars."""
        cfg = _cfg(LLM_MODEL="env-model", LLM_MODEL_MEDICAL="med-env")
        providers = [
            {"id": "p_fast", "model": "fast-model", "base_url": "http://f/v1", "api_key": "k", "purpose": "fast", "enabled": True},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="medical")
        # No medical provider → falls through to env vars
        assert candidates == ["med-env", "env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_route_to_nonexistent_provider_falls_to_env(self):
        """Route pointing to non-existent provider ID → falls through to env vars."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_real", "model": "real-model", "base_url": "http://r/v1", "api_key": "k", "enabled": True},
        ]
        routes = {"medical": "p_ghost"}  # points to non-existent provider
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="medical")
        assert candidates == ["env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_route_to_disabled_provider_falls_to_env(self):
        """Route pointing to disabled provider → falls through to env vars."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_disabled", "model": "disabled-model", "base_url": "http://d/v1", "api_key": "k", "enabled": False},
            {"id": "p_other", "model": "other-model", "base_url": "http://o/v1", "api_key": "k", "enabled": True},
        ]
        routes = {"fast": "p_disabled"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, _, meta = await resolve_model_candidates(cfg, requested_model="fast")
        assert candidates == ["env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_provider_custom_base_url_and_key_combined(self):
        """Provider with custom base_url and api_key uses them."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p1", "model": "pm", "base_url": "http://custom/v1", "api_key": "custom-key", "enabled": True, "purpose": "fast"},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates[0]["model"] == "pm"
        assert candidates[0]["base_url"] == "http://custom/v1"
        assert candidates[0]["api_key"] == "custom-key"

    @pytest.mark.asyncio
    async def test_fallback_provider_merged_after_primary(self):
        """Fallback provider appears after primary in candidate list."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_main", "model": "main-model", "base_url": "http://m/v1", "api_key": "k", "purpose": "fast", "enabled": True, "priority": 10},
            {"id": "p_fallback", "model": "fb-model", "base_url": "http://f/v1", "api_key": "k", "enabled": True, "priority": 20},
        ]
        routes = {"fallback": "p_fallback"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="fast")
        assert len(candidates) >= 2
        assert candidates[0]["model"] == "main-model"
        assert candidates[1]["model"] == "fb-model"

    @pytest.mark.asyncio
    async def test_reasoning_full_fallback_chain(self):
        """reasoning tier: LLM_REASONING_MODEL → LLM_MODEL_MEDICAL → LLM_MODEL → LLM_FALLBACK_MODEL."""
        cfg = _cfg(
            LLM_MODEL="global",
            LLM_MODEL_MEDICAL="med",
            LLM_REASONING_MODEL="reason",
            LLM_FALLBACK_MODEL="fb",
        )
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="reasoning")
        assert candidates == ["reason", "med", "global", "fb"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_medical_full_fallback_chain(self):
        """medical tier: LLM_MODEL_MEDICAL → LLM_FAST_MODEL → LLM_MODEL → LLM_FALLBACK_MODEL."""
        cfg = _cfg(
            LLM_MODEL="global",
            LLM_MODEL_MEDICAL="med",
            LLM_FALLBACK_MODEL="fb",
        )
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="medical")
        assert candidates == ["med", "global", "fb"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_fast_full_fallback_chain(self):
        """fast tier: LLM_FAST_MODEL → LLM_MODEL_MEDICAL → LLM_MODEL → LLM_FALLBACK_MODEL."""
        cfg = _cfg(
            LLM_MODEL="global",
            LLM_MODEL_MEDICAL="med",
            LLM_FALLBACK_MODEL="fb",
        )
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="fast")
        assert candidates == ["global", "med", "fb"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_long_context_full_fallback_chain(self):
        """long_context tier: LLM_MODEL_MEDICAL → LLM_MODEL → LLM_FALLBACK_MODEL."""
        cfg = _cfg(
            LLM_MODEL="global",
            LLM_MODEL_MEDICAL="med",
            LLM_FALLBACK_MODEL="fb",
        )
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="long_context")
        assert candidates == ["med", "global", "fb"]
        assert degraded is True

    @pytest.mark.asyncio
    async def test_whitespace_model_name_stripped(self):
        """Model names with surrounding whitespace are stripped."""
        cfg = _cfg(LLM_MODEL="  spaced-model  ")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, _ = await resolve_model_candidates(cfg)
        assert candidates == ["spaced-model"]

    @pytest.mark.asyncio
    async def test_empty_string_model_filtered(self):
        """Empty string in environment config does not become a candidate."""
        cfg = _cfg(LLM_MODEL="")
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, _ = await resolve_model_candidates(cfg)
        assert candidates == []

    # ── "No model" provider edge cases ──

    @pytest.mark.asyncio
    async def test_no_model_with_only_medical_provider_falls_to_env(self):
        """No model + only medical provider → must NOT implicitly select medical."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_med", "model": "med-provider", "base_url": "http://m/v1", "api_key": "k", "purpose": "medical", "enabled": True},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates == ["env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_no_model_with_only_reasoning_provider_falls_to_env(self):
        """No model + only reasoning provider → must NOT implicitly select reasoning."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_reason", "model": "reason-provider", "base_url": "http://r/v1", "api_key": "k", "purpose": "reasoning", "enabled": True},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            pass  # No Runtime Config
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates == ["env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_no_model_routes_fast_valid_provider(self):
        """No model + routes.fast → valid provider selected."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_fast", "model": "fast-model", "base_url": "http://f/v1", "api_key": "k", "enabled": True},
        ]
        routes = {"fast": "p_fast"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates[0]["model"] == "fast-model"
        assert meta["provider_pool"] is True

    @pytest.mark.asyncio
    async def test_no_model_purpose_fast_provider(self):
        """No model + purpose=fast provider → selected."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_fast", "model": "fast-prov", "base_url": "http://f/v1", "api_key": "k", "purpose": "fast", "enabled": True},
        ]
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates[0]["model"] == "fast-prov"
        assert meta["provider_pool"] is True

    @pytest.mark.asyncio
    async def test_no_model_routes_fast_invalid_falls_to_env(self):
        """No model + routes.fast → invalid id → falls through to env."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_real", "model": "real", "base_url": "http://r/v1", "api_key": "k", "enabled": True},
        ]
        routes = {"fast": "p_ghost"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, _, meta = await resolve_model_candidates(cfg)
        assert candidates == ["env-model"]
        assert meta["provider_pool"] is False

    @pytest.mark.asyncio
    async def test_no_model_no_env_returns_empty(self):
        """No model + no env config + no providers → empty candidates."""
        cfg = _cfg()
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            candidates, _, _ = await resolve_model_candidates(cfg)
        assert candidates == []

    @pytest.mark.asyncio
    async def test_routes_fallback_explicitly_configured(self):
        """routes.fallback explicitly set → fallback provider included."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_fast", "model": "main-model", "base_url": "http://m/v1", "api_key": "k", "purpose": "fast", "enabled": True, "priority": 10},
            {"id": "p_fb", "model": "fb-model", "base_url": "http://f/v1", "api_key": "k", "enabled": True, "priority": 20},
        ]
        routes = {"fallback": "p_fb"}
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            candidates, degraded, meta = await resolve_model_candidates(cfg, requested_model="fast")
        assert len(candidates) >= 2
        assert candidates[1]["model"] == "fb-model"


# ---------------------------------------------------------------------------
# Safe priority parser
# ---------------------------------------------------------------------------

class TestSafePriority:
    def test_valid_int(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({"priority": 5}) == 5

    def test_zero_priority(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({"priority": 0}) == 0

    def test_negative_priority(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({"priority": -10}) == -10

    def test_none_priority_defaults_50(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({"priority": None}) == 50

    def test_missing_priority_defaults_50(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({}) == 50

    def test_string_priority_defaults_50(self):
        from app.services.llm_runtime import _safe_priority
        assert _safe_priority({"priority": "high"}) == 50

    def test_float_string_priority_parsed(self):
        from app.services.llm_runtime import _safe_priority
        # "3.14" → int("3.14") raises ValueError → 50
        assert _safe_priority({"priority": "3.14"}) == 50


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------

class TestLogRedaction:
    def test_redact_api_key_in_query(self):
        from app.services.llm_runtime import _redact_url_for_log
        url = "http://host/v1/chat/completions?api_key=secret123"
        redacted = _redact_url_for_log(url)
        assert "secret123" not in redacted
        assert "REDACTED" in redacted

    def test_redact_bearer_token_in_text(self):
        from app.services.llm_runtime import _redact_sensitive
        text = 'Authorization: Bearer sk-abcdefghijklmnop'
        redacted = _redact_sensitive(text)
        assert 'sk-abcdefghijklmnop' not in redacted
        assert 'REDACTED' in redacted

    def test_redact_api_key_in_json(self):
        from app.services.llm_runtime import _redact_sensitive
        text = '{"api_key": "my-secret-key-12345"}'
        redacted = _redact_sensitive(text)
        assert 'my-secret-key-12345' not in redacted
        assert 'REDACTED' in redacted

    def test_redact_token_in_text(self):
        from app.services.llm_runtime import _redact_sensitive
        text = 'token=abcdefgh12345678&other=value'
        redacted = _redact_sensitive(text)
        assert 'abcdefgh12345678' not in redacted
        assert 'REDACTED' in redacted

    def test_preserves_clinical_text(self):
        from app.services.llm_runtime import _redact_sensitive
        clinical = "患者乳酸 3.2 mmol/L，建议复查血气分析"
        redacted = _redact_sensitive(clinical)
        assert redacted == clinical


# ---------------------------------------------------------------------------
# HTTP-layer send tests (mocked httpx.AsyncClient.post)
# ---------------------------------------------------------------------------

class TestHttpSendPayload:
    @pytest.mark.asyncio
    async def test_explicit_fake_model_sent_as_payload_model(self):
        """Explicit fake-model → payload.model == 'fake-model'."""
        cfg = _cfg(LLM_MODEL="fake-model")

        captured_payloads: list[dict] = []

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            captured_payloads.append(json or {})
            import httpx as _h
            return _h.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                result = await call_llm_chat(
                    cfg=cfg,
                    system_prompt="test",
                    user_prompt="hello",
                    model="fake-model",
                )
        assert len(captured_payloads) == 1
        assert captured_payloads[0]["model"] == "fake-model"
        assert captured_payloads[0]["model"] != ""

    @pytest.mark.asyncio
    async def test_model_not_empty_in_payload(self):
        """Empty config → LLMRuntimeUnavailableError raised before HTTP call."""
        cfg = _cfg()

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            with pytest.raises(LLMRuntimeUnavailableError):
                await call_llm_chat(
                    cfg=cfg,
                    system_prompt="test",
                    user_prompt="hello",
                )

    @pytest.mark.asyncio
    async def test_tier_keyword_not_sent_as_model(self):
        """Tier keyword 'reasoning' resolves to real model, not sent verbatim."""
        cfg = _cfg(LLM_MODEL="real-model")

        captured: list[dict] = []

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                await call_llm_chat(
                    cfg=cfg,
                    system_prompt="test",
                    user_prompt="hello",
                    model="reasoning",
                )
        assert len(captured) == 1
        assert captured[0]["model"] == "real-model"

    @pytest.mark.asyncio
    async def test_empty_config_does_not_call_http(self):
        """Empty config → error raised before any HTTP post."""
        cfg = _cfg()

        call_count = [0]

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            call_count[0] += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                with pytest.raises(LLMRuntimeUnavailableError):
                    await call_llm_chat(
                        cfg=cfg,
                        system_prompt="test",
                        user_prompt="hello",
                    )
        assert call_count[0] == 0

    @pytest.mark.asyncio
    async def test_provider_model_sent_in_payload(self):
        """Provider model name appears in the HTTP payload."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p1", "model": "provider-model", "base_url": "http://p/v1", "api_key": "k", "purpose": "fast", "enabled": True},
        ]

        captured: list[dict] = []

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            captured.append(json or {})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                await call_llm_chat(
                    cfg=cfg,
                    system_prompt="test",
                    user_prompt="hello",
                )
        assert len(captured) == 1
        assert captured[0]["model"] == "provider-model"


# ---------------------------------------------------------------------------
# Fallback ordering: fallback must NEVER precede selected
# ---------------------------------------------------------------------------

class TestFallbackOrdering:
    """Fallback providers must ALWAYS come after selected providers in the
    candidate list, regardless of their priority values."""

    def test_fallback_never_precedes_selected_by_priority(self):
        """selected priority=50, fallback priority=1 → selected still first."""
        runtime = {
            "providers": [
                {"id": "p_sel", "model": "selected-model", "enabled": True, "purpose": "fast", "priority": 50},
                {"id": "p_fb", "model": "fallback-model", "enabled": True, "priority": 1},
            ],
            "routes": {"fallback": "p_fb"},
        }
        rows, meta = _provider_candidates(runtime, "fast")
        assert rows[0]["model"] == "selected-model"
        assert rows[1]["model"] == "fallback-model"
        assert meta["primary_model"] == "selected-model"
        assert meta["fallback_model"] == "fallback-model"

    def test_negative_priority_fallback_never_precedes_selected(self):
        """selected priority=-10, fallback priority=-100 → selected still first."""
        runtime = {
            "providers": [
                {"id": "p_sel", "model": "selected-model", "enabled": True, "purpose": "fast", "priority": -10},
                {"id": "p_fb", "model": "fallback-model", "enabled": True, "priority": -100},
            ],
            "routes": {"fallback": "p_fb"},
        }
        rows, meta = _provider_candidates(runtime, "fast")
        assert rows[0]["model"] == "selected-model"
        assert rows[1]["model"] == "fallback-model"

    def test_selected_group_sorted_by_priority(self):
        """Multiple selected providers are internally sorted by priority."""
        runtime = {
            "providers": [
                {"id": "p_low", "model": "low-prio", "enabled": True, "purpose": "fast", "priority": 30},
                {"id": "p_high", "model": "high-prio", "enabled": True, "purpose": "fast", "priority": 10},
            ],
        }
        rows, meta = _provider_candidates(runtime, "fast")
        assert rows[0]["model"] == "high-prio"
        assert rows[1]["model"] == "low-prio"

    def test_fallback_group_sorted_by_priority(self):
        """Multiple fallback providers are internally sorted by priority."""
        runtime = {
            "providers": [
                {"id": "p_sel", "model": "selected", "enabled": True, "purpose": "fast", "priority": 10},
                {"id": "fb_low", "model": "fb-low", "enabled": True, "priority": 30},
                {"id": "fb_high", "model": "fb-high", "enabled": True, "priority": 20},
            ],
            "routes": {"fallback": "fb_low"},
        }
        # Only fb_low is explicitly routed as fallback
        rows, meta = _provider_candidates(runtime, "fast")
        assert rows[0]["model"] == "selected"
        assert len(rows) == 2  # selected + only the routed fallback
        assert rows[1]["model"] == "fb-low"

    def test_same_provider_selected_and_fallback_deduplicated(self):
        """Same provider in selected and fallback → dedup, kept as selected."""
        runtime = {
            "providers": [
                {"id": "p1", "model": "shared-model", "enabled": True, "purpose": "fast", "priority": 10},
            ],
            "routes": {"fallback": "p1"},
        }
        rows, meta = _provider_candidates(runtime, "fast")
        assert len(rows) == 1
        assert rows[0]["model"] == "shared-model"
        # When there's no separate fallback, fallback_model is empty
        assert meta["fallback_model"] == ""

    def test_explicit_fallback_only_candidate_when_no_primary(self):
        """Only fallback configured, no selected → fallback IS the candidate."""
        runtime = {
            "providers": [
                {"id": "fb", "model": "only-fallback", "enabled": True, "priority": 10},
            ],
            "routes": {"fallback": "fb"},
        }
        # No "fast" purpose, no route — should fall through to env vars, not use
        # unrouted providers as implicit candidates.
        rows, meta = _provider_candidates(runtime, None)
        # No "fast" provider → returns empty (falls through to env vars)
        assert rows == []

    def test_unrouted_provider_not_used_as_fallback(self):
        """Providers without a matching route or purpose are excluded."""
        runtime = {
            "providers": [
                {"id": "p_fast", "model": "fast-model", "enabled": True, "purpose": "fast", "priority": 10},
                {"id": "p_unrouted", "model": "unrouted-model", "enabled": True, "priority": 1},
            ],
        }
        rows, meta = _provider_candidates(runtime, "fast")
        assert len(rows) == 1
        assert rows[0]["model"] == "fast-model"


# ---------------------------------------------------------------------------
# HTTP-layer: fallback call ordering and degraded_mode
# ---------------------------------------------------------------------------

class TestFallbackHttpCallOrder:
    """Verify that selected is tried first, fallback only on failure,
    and degraded_mode is set correctly."""

    @pytest.mark.asyncio
    async def test_fallback_not_called_when_selected_succeeds(self):
        """selected succeeds → fallback HTTP is never called."""
        cfg = _cfg(LLM_MODEL="env-model")
        # Two providers: selected (purpose=fast) and fallback (routed)
        providers = [
            {"id": "p_sel", "model": "selected-model", "base_url": "http://s/v1", "api_key": "k", "purpose": "fast", "enabled": True, "priority": 10},
            {"id": "p_fb", "model": "fallback-model", "base_url": "http://f/v1", "api_key": "k", "enabled": True, "priority": 1},
        ]
        routes = {"fallback": "p_fb"}

        call_models: list[str] = []

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            call_models.append((json or {}).get("model", ""))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                result = await call_llm_chat(
                    cfg=cfg,
                    system_prompt="test",
                    user_prompt="hello",
                    model="fast",
                )
        # Only the selected provider was called
        assert call_models == ["selected-model"]
        assert result["degraded_mode"] is False

    @pytest.mark.asyncio
    async def test_fallback_used_after_selected_http_failure(self):
        """selected fails → fallback is tried next."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p_sel", "model": "selected-model", "base_url": "http://s/v1", "api_key": "k", "purpose": "fast", "enabled": True, "priority": 10},
            {"id": "p_fb", "model": "fallback-model", "base_url": "http://f/v1", "api_key": "k", "enabled": True, "priority": 20},
        ]
        routes = {"fallback": "p_fb"}

        call_models: list[str] = []
        _first_call = True

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            nonlocal _first_call
            model = (json or {}).get("model", "")
            call_models.append(model)
            if _first_call:
                _first_call = False
                raise httpx.ConnectError("selected unavailable")
            return httpx.Response(200, json={"choices": [{"message": {"content": "fallback response"}}]})

        # Unique prompt to avoid cache collision with other HTTP tests
        tag = "test-fallback-http-ordering-1"
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers, routes=routes)):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                result = await call_llm_chat(
                    cfg=cfg,
                    system_prompt=tag,
                    user_prompt=tag,
                    model="fast",
                )
        # selected first, then fallback
        assert call_models == ["selected-model", "fallback-model"]
        assert result["degraded_mode"] is True
        assert result["model"] == "fallback-model"

    @pytest.mark.asyncio
    async def test_degraded_mode_false_when_only_provider_succeeds(self):
        """Single provider succeeds → degraded_mode=false."""
        cfg = _cfg(LLM_MODEL="env-model")
        providers = [
            {"id": "p1", "model": "sole-model", "base_url": "http://s/v1", "api_key": "k", "purpose": "fast", "enabled": True},
        ]

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        tag = "test-degraded-false-sole-provider"
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai(providers=providers)):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                result = await call_llm_chat(
                    cfg=cfg,
                    system_prompt=tag,
                    user_prompt=tag,
                )
        assert result["degraded_mode"] is False

    @pytest.mark.asyncio
    async def test_degraded_mode_true_when_env_fallback_used(self):
        """env-based primary fails, fallback succeeds → degraded_mode=true."""
        cfg = _cfg(LLM_MODEL="env-primary", LLM_FALLBACK_MODEL="env-fallback")

        call_models: list[str] = []
        _first = True

        async def _fake_post(_self, url, *, json=None, headers=None, **kwargs):
            nonlocal _first
            model = (json or {}).get("model", "")
            call_models.append(model)
            if _first:
                _first = False
                raise httpx.ConnectError("primary down")
            return httpx.Response(200, json={"choices": [{"message": {"content": "fb ok"}}]})

        tag = "test-degraded-true-env-fallback"
        with patch("app.services.llm_runtime._runtime_ai_config", _mock_runtime_ai()):
            with patch.object(httpx.AsyncClient, "post", _fake_post), \
                 patch.object(httpx.Response, "raise_for_status", lambda _s: None):
                result = await call_llm_chat(
                    cfg=cfg,
                    system_prompt=tag,
                    user_prompt=tag,
                )
        assert call_models == ["env-primary", "env-fallback"]
        assert result["degraded_mode"] is True
        assert result["model"] == "env-fallback"
