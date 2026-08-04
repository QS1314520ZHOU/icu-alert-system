"""
测试 serve_frontend 路径穿越防护 + CSP 环境变量逻辑。

安全要求：
- ..、绝对路径、URL 编码 %2e%2e%2f 等输入必须返回 404，不得泄露 STATIC_DIR 之外的文件。
- SMARTCARE_EMBED_FRAME_ANCESTORS 环境变量控制 CSP 头输出，必须双向覆盖。
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 构造一个最小的 FastAPI app，复用 main.py 的 _is_within_static + CSP 逻辑
# ---------------------------------------------------------------------------

def _make_app(static_dir: str) -> FastAPI:
    """创建一个包含路径穿越防护 + CSP 逻辑的测试用 app。"""
    app = FastAPI()
    _static_real = os.path.realpath(static_dir)

    def _is_within_static(requested_path: str) -> bool:
        real = os.path.realpath(requested_path)
        try:
            return os.path.commonpath([real, _static_real]) == _static_real
        except ValueError:
            # Windows 上不同盘符会抛 ValueError（如 C: vs D:）
            return False

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        raw_path = os.path.join(static_dir, full_path)
        if not _is_within_static(raw_path):
            raise HTTPException(status_code=404, detail="Not found")

        if os.path.isfile(raw_path):
            resp = FileResponse(raw_path)
            if full_path == "embed.html":
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                allowed = os.environ.get("SMARTCARE_EMBED_FRAME_ANCESTORS", "").strip()
                if allowed:
                    origins = " ".join(o.strip() for o in allowed.split(",") if o.strip())
                    resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {origins};"
            return resp

        raise HTTPException(status_code=404, detail="Not found")

    return app


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

@pytest.fixture
def static_server(tmp_path: Path):
    """创建临时静态目录和测试文件。"""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>index</h1>")
    (static_dir / "embed.html").write_text("<h1>embed</h1>")
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("console.log('ok')")

    app = _make_app(str(static_dir))
    client = TestClient(app, raise_server_exceptions=False)
    return client, static_dir


def test_normal_file_returns_200(static_server):
    """正常文件应返回 200。"""
    client, _ = static_server
    resp = client.get("/embed.html")
    assert resp.status_code == 200


def test_dotdot_returns_404(static_server):
    """../../etc/passwd 应返回 404。"""
    client, _ = static_server
    resp = client.get("/../../etc/passwd")
    assert resp.status_code == 404


def test_absolute_path_returns_404(static_server):
    """绝对路径 /etc/passwd 应返回 404。"""
    client, _ = static_server
    resp = client.get("/etc/passwd")
    assert resp.status_code == 404


def test_url_encoded_dotdot_returns_404(static_server):
    """URL 编码 %2e%2e%2f 应返回 404。"""
    client, _ = static_server
    # %2e = ., %2f = /
    resp = client.get("/%2e%2e/%2e%2e/etc/passwd")
    assert resp.status_code == 404


def test_double_dotdot_returns_404(static_server):
    """../../../etc/passwd 应返回 404。"""
    client, _ = static_server
    resp = client.get("/../../../etc/passwd")
    assert resp.status_code == 404


def test_subdirectory_file_returns_200(static_server):
    """子目录下的文件应正常返回 200。"""
    client, _ = static_server
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200


def test_nested_dotdot_returns_404(static_server):
    """assets/../../etc/passwd 应返回 404。"""
    client, _ = static_server
    resp = client.get("/assets/../../etc/passwd")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CSP 环境变量测试
# ---------------------------------------------------------------------------

class TestCspEnvironmentVariable:
    """SMARTCARE_EMBED_FRAME_ANCESTORS 环境变量的双向测试。"""

    def test_single_origin_adds_csp(self, static_server, monkeypatch):
        """配置单个 origin 时，响应应包含 CSP 头且值正确。"""
        client, _ = static_server
        monkeypatch.setenv("SMARTCARE_EMBED_FRAME_ANCESTORS", "http://10.0.0.9:8080")
        resp = client.get("/embed.html")
        assert resp.status_code == 200
        csp = resp.headers.get("content-security-policy", "")
        assert csp == "frame-ancestors 'self' http://10.0.0.9:8080;"
        assert "'self'" in csp

    def test_multiple_origins_comma_separated(self, static_server, monkeypatch):
        """多个 origin 逗号分隔时，应被拆分为空格分隔且无残留逗号。"""
        client, _ = static_server
        monkeypatch.setenv(
            "SMARTCARE_EMBED_FRAME_ANCESTORS",
            "http://10.0.0.9:8080,http://10.0.0.9,https://example.com"
        )
        resp = client.get("/embed.html")
        csp = resp.headers.get("content-security-policy", "")
        assert csp == "frame-ancestors 'self' http://10.0.0.9:8080 http://10.0.0.9 https://example.com;"
        assert "," not in csp

    def test_no_env_var_no_csp(self, static_server, monkeypatch):
        """未配置环境变量时，响应不应包含 CSP 头，但 Cache-Control 仍存在。"""
        client, _ = static_server
        monkeypatch.delenv("SMARTCARE_EMBED_FRAME_ANCESTORS", raising=False)
        resp = client.get("/embed.html")
        assert resp.status_code == 200
        assert "content-security-policy" not in resp.headers
        assert "no-cache" in resp.headers.get("cache-control", "")

    def test_csp_value_no_angle_brackets(self, static_server, monkeypatch):
        """CSP 值中不应包含尖括号（防止占位符回归）。"""
        client, _ = static_server
        monkeypatch.setenv("SMARTCARE_EMBED_FRAME_ANCESTORS", "http://10.0.0.9:8080")
        resp = client.get("/embed.html")
        csp = resp.headers.get("content-security-policy", "")
        assert "<" not in csp
        assert ">" not in csp

    def test_empty_env_var_no_csp(self, static_server, monkeypatch):
        """空字符串环境变量时，不应输出 CSP 头。"""
        client, _ = static_server
        monkeypatch.setenv("SMARTCARE_EMBED_FRAME_ANCESTORS", "")
        resp = client.get("/embed.html")
        assert "content-security-policy" not in resp.headers

    def test_whitespace_only_env_var_no_csp(self, static_server, monkeypatch):
        """纯空格环境变量时，不应输出 CSP 头。"""
        client, _ = static_server
        monkeypatch.setenv("SMARTCARE_EMBED_FRAME_ANCESTORS", "   ")
        resp = client.get("/embed.html")
        assert "content-security-policy" not in resp.headers


# ---------------------------------------------------------------------------
# Windows 跨盘符 ValueError 分支测试
# ---------------------------------------------------------------------------

class TestIsWithinStaticCrossDrive:
    """覆盖 _is_within_static 的 except ValueError 分支。"""

    def test_valueerror_returns_false(self):
        """monkeypatch 让 os.path.commonpath 抛 ValueError，应返回 False。"""
        with patch("os.path.commonpath", side_effect=ValueError("test")):
            from app.main import _is_within_static
            result = _is_within_static("D:/foo")
            assert result is False

    @pytest.mark.skipif(os.name != "nt", reason="Windows only")
    def test_different_drive_returns_404(self, static_server):
        """Windows 不同盘符路径应返回 404。"""
        client, _ = static_server
        resp = client.get("/D:/foo/bar")
        assert resp.status_code == 404
