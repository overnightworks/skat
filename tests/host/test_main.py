import pytest
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

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


def without_password(database_url: str) -> str:
    return make_url(database_url).set(drivername="postgresql", password=None).render_as_string()


@pytest.fixture
def engine_urls(monkeypatch):
    """The URLs `main` builds its engines on; the engines are the real ones."""
    urls = []
    real_create_store_engine = create_store_engine

    def recording(database_url):
        engine = real_create_store_engine(database_url)
        urls.append(engine.url)
        return engine

    monkeypatch.setattr("skat.host.main.create_store_engine", recording)
    return urls


@pytest.fixture
def configured_environment(sign_in_settings, monkeypatch, tmp_path):
    def configure(database_url: str | None = None, **overrides: object) -> None:
        if database_url is not None:
            overrides["database_url"] = without_password(database_url)
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

    def test_refuses_to_serve_when_the_database_password_file_cannot_be_read(
        self, server, configured_environment, tmp_path
    ):
        configured_environment(database_password_file=tmp_path / "missing-file")

        with pytest.raises(StartRefusedError, match="database_password_file"):
            main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

    @pytest.mark.parametrize("password", ["a-b_c", "-_", "p@ss/w:rd?#%"])
    def test_serves_on_the_database_url_with_the_password_from_its_file_whatever_its_characters(
        self, server, configured_environment, database_url, engine_urls, tmp_path, password
    ):
        password_file = tmp_path / "password-of-the-test"
        password_file.write_text(password + "\n")
        configured_environment(database_url, database_password_file=password_file)

        main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

        [url] = engine_urls
        expected = make_url(database_url)
        assert (url.password, url.host, url.port, url.username, url.database) == (
            password,
            expected.host,
            expected.port,
            expected.username,
            expected.database,
        )

    def test_logs_and_prints_no_part_of_the_database_password_on_a_start(
        self, server, configured_environment, database_url, sign_in_settings, capsys, caplog
    ):
        sign_in = sign_in_settings()
        configured_environment(database_url, database_password_file=sign_in.settings.database_password_file)

        main(["serve"], run_server=server, build_directory=FIXTURE_DIRECTORY)

        output = capsys.readouterr()
        assert sign_in.database_password not in output.out + output.err + caplog.text

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
        password_file = tmp_path / "password-of-the-test"
        password_file.write_text("password-of-the-test\n")
        monkeypatch.setenv("SKAT_DATABASE_URL", without_password(unmigrated_database_url))
        monkeypatch.setenv("SKAT_DATABASE_PASSWORD_FILE", str(password_file))
        return unmigrated_database_url

    def test_migrates_on_the_database_url_with_the_password_from_its_file(self, only_the_database_setting, engine_urls):
        main(["migrate"])

        [url] = engine_urls
        assert url.password == "password-of-the-test"
        assert url.database == make_url(only_the_database_setting).database

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


class TestRefusedDatabaseSettings:
    @pytest.mark.parametrize("command", ["serve", "migrate"])
    def test_refuses_a_database_url_with_a_password_naming_the_setting_and_echoing_neither(
        self, command, configured_environment, monkeypatch
    ):
        password = "pw-of-the-test_1"
        url = f"postgresql://skat:{password}@postgres/skat"
        configured_environment()
        monkeypatch.setenv("SKAT_DATABASE_URL", url)

        with pytest.raises(ValidationError, match="database_url") as refusal:
            main([command], build_directory=FIXTURE_DIRECTORY)

        assert password not in str(refusal.value)
        assert url not in str(refusal.value)

    @pytest.mark.parametrize("command", ["serve", "migrate"])
    def test_refuses_when_only_the_retired_database_url_file_is_set(
        self, command, configured_environment, monkeypatch, tmp_path
    ):
        configured_environment()
        monkeypatch.delenv("SKAT_DATABASE_URL")
        monkeypatch.setenv("SKAT_DATABASE_URL_FILE", str(tmp_path / "database-url"))

        with pytest.raises(ValidationError, match="database_url"):
            main([command], build_directory=FIXTURE_DIRECTORY)


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
