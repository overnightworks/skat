import pytest

from skat.host.main import main, uvicorn_options
from skat.web.constants import UVICORN_LOG_LEVEL
from skat.web.secret_files import StartRefusedError
from tests.support.page_build import FIXTURE_DIRECTORY


class ServerRecorder:
    """Stands in for the server runner and keeps what it was asked to run."""

    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []

    def __call__(self, app, **options) -> None:
        self.runs.append({"app": app, **options})


@pytest.fixture
def server() -> ServerRecorder:
    return ServerRecorder()


@pytest.fixture
def configured_environment(sign_in_settings, monkeypatch):
    def configure(**overrides: object) -> None:
        for name, value in sign_in_settings(**overrides).environment.items():
            monkeypatch.setenv(name, value)

    return configure


class TestMain:
    def test_starts_server_with_configured_host_and_port(self, server, configured_environment):
        configured_environment(host="127.0.0.1", port=9090)
        main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)
        assert [(run["host"], run["port"]) for run in server.runs] == [("127.0.0.1", 9090)]

    def test_refuses_to_start_without_the_page_build_and_names_the_build_command(
        self, server, configured_environment, tmp_path
    ):
        configured_environment()

        with pytest.raises(StartRefusedError, match="make frontend"):
            main(["serve"], run_server=server, build_directory=tmp_path / "build")

        assert server.runs == []

    @pytest.mark.parametrize("arguments", [[], ["frobnicate"]])
    def test_refuses_without_the_serve_command_and_starts_nothing(self, server, arguments, capsys):
        with pytest.raises(SystemExit) as refusal:
            main(arguments, run_server=server, build_directory=FIXTURE_DIRECTORY)
        assert refusal.value.code != 0
        assert "serve" in capsys.readouterr().err
        assert server.runs == []


class TestUvicornOptions:
    def test_writes_no_access_line_and_logs_only_warnings(self, sign_in_settings):
        options = uvicorn_options(sign_in_settings().settings)
        assert options["access_log"] is False
        assert options["log_level"] == UVICORN_LOG_LEVEL

    def test_leaves_the_client_address_to_the_trusted_proxy_setting(self, sign_in_settings):
        assert uvicorn_options(sign_in_settings().settings)["proxy_headers"] is False
