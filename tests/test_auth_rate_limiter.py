import time
from datetime import timedelta

import pytest

from trh.auth.rate_limiter import RateLimiter


def test_rate_limiter_allows_requests_up_to_limit():
    limiter = RateLimiter(max_attempts=3, window_minutes=5)

    assert limiter.is_allowed("key") is True
    assert limiter.is_allowed("key") is True
    assert limiter.is_allowed("key") is True
    assert limiter.is_allowed("key") is False


def test_rate_limiter_tracks_keys_independently():
    limiter = RateLimiter(max_attempts=2, window_minutes=5)

    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("a") is True
    assert limiter.is_allowed("b") is True
    assert limiter.is_allowed("a") is False
    assert limiter.is_allowed("b") is True


def test_rate_limiter_sliding_window_ages_out_old_attempts():
    # Re-create with a very short window to avoid sleeping in tests
    short_limiter = RateLimiter(max_attempts=2, window_minutes=5)
    short_limiter.window = timedelta(seconds=0.05)

    assert short_limiter.is_allowed("key") is True
    assert short_limiter.is_allowed("key") is True
    assert short_limiter.is_allowed("key") is False

    time.sleep(0.06)

    assert short_limiter.is_allowed("key") is True


def test_rate_limiter_reset_clears_attempts():
    limiter = RateLimiter(max_attempts=1, window_minutes=5)

    assert limiter.is_allowed("key") is True
    assert limiter.is_allowed("key") is False

    limiter.reset("key")

    assert limiter.is_allowed("key") is True
