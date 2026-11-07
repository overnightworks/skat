import pytest

from tests.web.support.skat import Skat


@pytest.fixture
def skat(sign_in_settings):
    return Skat(sign_in_settings)
