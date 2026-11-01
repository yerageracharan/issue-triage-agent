import pytest

pytest.importorskip("mcp")

from issue_triage_agent import mcp_server


def test_mcp_server_defaults_to_stdio():
    args = mcp_server.build_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_mcp_server_accepts_streamable_http():
    args = mcp_server.build_parser().parse_args(["--transport", "streamable-http", "--port", "8123"])
    assert args.transport == "streamable-http"
    assert args.port == 8123
