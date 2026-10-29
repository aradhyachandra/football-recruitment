from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sb_raw():
    return FIXTURES / "statsbomb"


@pytest.fixture
def tm_raw():
    return FIXTURES / "transfermarkt"


@pytest.fixture
def fields():
    from recruit import config
    return config.load("statsbomb_fields")
