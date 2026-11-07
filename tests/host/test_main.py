import pytest
from sqlalchemy import inspect

from skat.host.main import main, uvicorn_options
from skat.store.migrate import DatabaseNotAtHeadError, create_store_engine
from skat.web.constants import UVICORN_LOG_LEVEL
from skat.web.secret_files import StartRefusedError
from tests.e2e.support.server import SERVER_STOP_TIMEOUT_SECONDS
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
def configured_environment(sign_in_settings, monkeypatch, tmp_path):
    def configure(database_url: str | None = None, **overrides: object) -> None:
        if database_url is not None:
            database_url_file = tmp_path / "database-url-of-the-test"
            database_url_file.write_text(database_url + "\n")
            overrides["database_url_file"] = database_url_file
        for name, value in sign_in_settings(**overrides).environment.items():
            monkeypatch.setenv(name, value)

    return configure


@pytest.mark.postgres
class TestMain:
    def test_starts_server_with_configured_host_and_port(self, server, configured_environment, database_url):
        configured_environment(database_url, host="127.0.0.1", port=9090)
        main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)
        assert [(run["host"], run["port"]) for run in server.runs] == [("127.0.0.1", 9090)]

    def test_refuses_to_start_without_the_page_build_and_names_the_build_command(
        self, server, configured_environment, database_url, tmp_path
    ):
        configured_environment(database_url)

        with pytest.raises(StartRefusedError, match="make frontend"):
            main(["serve"], run_server=server, build_directory=tmp_path / "build")

        assert server.runs == []

    def test_refuses_to_serve_a_database_that_is_not_at_head_and_starts_nothing(
        self, server, configured_environment, unmigrated_database_url
    ):
        configured_environment(unmigrated_database_url)

        with pytest.raises(DatabaseNotAtHeadError, match="skat migrate"):
            main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

        assert server.runs == []

    def test_refuses_to_serve_when_the_database_url_file_cannot_be_read(self, server, configured_environment, tmp_path):
        configured_environment(database_url_file=tmp_path / "missing-file")

        with pytest.raises(StartRefusedError, match="database_url_file"):
            main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

    @pytest.mark.parametrize("arguments", [[], ["frobnicate"]])
    def test_refuses_without_the_serve_command_and_starts_nothing(self, server, arguments, capsys):
        with pytest.raises(SystemExit) as refusal:
            main(arguments, run_server=server, build_directory=FIXTURE_DIRECTORY)
        assert refusal.value.code != 0
        assert "serve" in capsys.readouterr().err
        assert server.runs == []


@pytest.mark.postgres
class TestMigrate:
    @pytest.fixture
    def only_the_database_setting(self, monkeypatch, tmp_path, unmigrated_database_url):
        database_url_file = tmp_path / "database-url-of-the-test"
        database_url_file.write_text(unmigrated_database_url + "\n")
        monkeypatch.setenv("SKAT_DATABASE_URL_FILE", str(database_url_file))
        return unmigrated_database_url

    def test_migrates_with_no_other_setting_and_no_page_build(self, only_the_database_setting):
        main(["migrate"])

        engine = create_store_engine(only_the_database_setting)
        assert {"tables", "chairs", "receipts"} <= set(inspect(engine).get_table_names())
        engine.dispose()

    def test_leaves_a_database_that_serve_then_accepts(self, only_the_database_setting, server, configured_environment):
        main(["migrate"])
        main(["migrate"])
        configured_environment(only_the_database_setting)

        main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

        assert len(server.runs) == 1


class TestUvicornOptions:
    def test_writes_no_access_line_and_logs_only_warnings(self, sign_in_settings):
        options = uvicorn_options(sign_in_settings().settings)
        assert options["access_log"] is False
        assert options["log_level"] == UVICORN_LOG_LEVEL

    def test_leaves_the_client_address_to_the_trusted_proxy_setting(self, sign_in_settings):
        assert uvicorn_options(sign_in_settings().settings)["proxy_headers"] is False

    def test_cancels_open_streams_before_the_end_to_end_server_gives_up_waiting(self, sign_in_settings):
        timeout = uvicorn_options(sign_in_settings().settings)["timeout_graceful_shutdown"]

        assert 0 < timeout < SERVER_STOP_TIMEOUT_SECONDS
