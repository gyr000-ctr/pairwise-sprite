import math

import pytest

import sprite

def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False

def _a():
    return sprite.Animation(4, 10.0)


def _check_frame_zero():
    return _a().frame_at(0.0) == 0


def _check_frame_one():
    return _a().frame_at(0.1) == 1


def _check_frame_wrap():
    return _a().frame_at(0.4) == 0


def _check_no_loop():
    return _a().frame_at(10.0, loop=False) == 3


def _check_bad_frames():
    return _raises(lambda: sprite.Animation(0, 10.0))


def _check_bad_fps():
    return _raises(lambda: sprite.Animation(4, 0.0))


def _check_negative():
    return _raises(lambda: _a().frame_at(-0.1))


def _check_det():
    return _a().frame_at(0.25) == _a().frame_at(0.25)


def _check_type():
    return isinstance(_a().frame_at(0.0), int)


def _check_bounds():
    return 0 <= _a().frame_at(0.99) <= 3


def _check_last():
    return _a().frame_at(0.3) == 3


def _check_partial():
    return _a().frame_at(0.05) == 0


def _check_two():
    return _a().frame_at(0.5) == 1


def _check_float():
    return _a().frame_at(0.15) == 1


def _check_no_mut():
    a = _a()
    a.frame_at(0.1)
    return a.frame_at(0.0) == 0

CASES = [("frame_zero", "_check_frame_zero"), ("frame_one", "_check_frame_one"), ("frame_wrap", "_check_frame_wrap"), ("no_loop", "_check_no_loop"), ("bad_frames", "_check_bad_frames"), ("bad_fps", "_check_bad_fps"), ("negative", "_check_negative"), ("det", "_check_det"), ("type", "_check_type"), ("bounds", "_check_bounds"), ("last", "_check_last"), ("partial", "_check_partial"), ("two", "_check_two"), ("float", "_check_float"), ("no_mut", "_check_no_mut")]


@pytest.mark.parametrize("name,check", CASES, ids=[c[0] for c in CASES])
def test_spec(name, check):
    assert globals()[check]() is True
