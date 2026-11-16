"""What the calls to the issuer write to the log: one line each with the outcome, never a request or an answer."""

import pytest
from logline import Outcome
from pydantic import SecretStr
from webauth.oidc import TokenEndpointAnswer, TokenEndpointError, TokenRequest

from skat.web.sign_in import IssuerRefusal, IssuerTransports, timed_issuer_calls
from tests.support.log_lines import lines_of, logged

REQUEST = TokenRequest(url="https://issuer.test/token", form={}, authorization=SecretStr("Basic secret"))


def issuer_answering(status):
    return IssuerTransports(
        post_token_request=lambda _request: TokenEndpointAnswer(status, b"the answer"),
        fetch_key_set=lambda _url: b"the keys",
    )


class TestTokenExchangeLine:
    @pytest.mark.parametrize(
        ("status", "outcome", "reason"),
        [(200, Outcome.OK, None), (400, Outcome.REFUSED, IssuerRefusal.ERROR_STATUS)],
        ids=["answered", "answered-an-error-status"],
    )
    def test_one_line_ends_ok_for_an_answer_and_refused_for_an_error_status(self, capsys, status, outcome, reason):
        with logged(capsys) as lines:
            answer = timed_issuer_calls(issuer_answering(status)).post_token_request(REQUEST)

        (line,) = lines_of(lines, "token_exchange.ended")
        assert (answer.status, line["outcome"], line.get("reason"), line["status"]) == (status, outcome, reason, status)
        assert line["duration_ms"] >= 0
        assert "secret" not in str(line)

    def test_an_issuer_that_cannot_be_reached_ends_the_line_failed_with_the_errors_type_and_raises_on(self, capsys):
        def unreachable(_request):
            raise TokenEndpointError("unreachable")

        transports = IssuerTransports(post_token_request=unreachable, fetch_key_set=lambda _url: b"")
        timed = timed_issuer_calls(transports)

        with logged(capsys) as lines, pytest.raises(TokenEndpointError):
            timed.post_token_request(REQUEST)

        (line,) = lines_of(lines, "token_exchange.ended")
        assert (line["outcome"], line["error_type"]) == (Outcome.FAILED, "TokenEndpointError")


class TestKeySetFetchLine:
    def test_one_ok_line_for_a_fetch_and_the_keys_pass_on_unchanged(self, capsys):
        with logged(capsys) as lines:
            keys = timed_issuer_calls(issuer_answering(200)).fetch_key_set("https://issuer.test/certs")

        (line,) = lines_of(lines, "key_set_fetch.ended")
        assert (keys, line["outcome"]) == (b"the keys", Outcome.OK)
