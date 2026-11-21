"""帧选择扩展测试：可变时长、往返播放、精度、并发、性能与错误区分。

所有用例命名均含 ``frame``，可被 ``pytest -k frame`` 收集。
"""

import threading
from fractions import Fraction

import pytest

import sprite
from sprite import (
    Animation,
    DurationError,
    FrameCountError,
    FrameRateError,
    InvalidTimeError,
    NegativeTimeError,
)


def make_frame_animation():
    return Animation(4, 10.0)


# --------------------------------------------------------------------- #
# 基础行为（与既有规格一致的补充断言）
# --------------------------------------------------------------------- #
def test_frame_basic_sequence():
    a = make_frame_animation()
    assert [a.frame_at(t) for t in (0.0, 0.1, 0.2, 0.3)] == [0, 1, 2, 3]


def test_frame_wrap_around():
    a = make_frame_animation()
    assert a.frame_at(0.4) == 0
    assert a.frame_at(0.5) == 1
    assert a.frame_at(1.2) == 0  # 第三次循环起点


def test_frame_no_loop_clamps_to_last_frame():
    a = make_frame_animation()
    assert a.frame_at(0.3, loop=False) == 3
    assert a.frame_at(10.0, loop=False) == 3
    assert a.frame_at(100.0, loop=False) == 3


def test_frame_always_in_bounds():
    a = make_frame_animation()
    for i in range(200):
        f = a.frame_at(i * 0.037)
        assert 0 <= f < 4
    assert a.frame_at(0.0) == 0


def test_frame_returns_plain_int():
    assert type(make_frame_animation().frame_at(0.25)) is int


def test_frame_stateless_and_deterministic():
    a = make_frame_animation()
    seq = [a.frame_at(0.1), a.frame_at(0.3), a.frame_at(0.0)]
    again = [a.frame_at(0.1), a.frame_at(0.3), a.frame_at(0.0)]
    assert seq == again == [1, 3, 0]


# --------------------------------------------------------------------- #
# 非整数 fps（隐藏用例方向）
# --------------------------------------------------------------------- #
def test_frame_non_integer_fps():
    # 29.97 fps：帧槽 floor(t * 29.97)
    a = Animation(30, 29.97)
    assert a.frame_at(0.0) == 0
    assert a.frame_at(1.0 / 29.97) == 1
    # 与分数精确值比对，避免浮点取整误差
    exact = Fraction(2997, 100)
    for t in ("0.5", "1.0", "3.3333333333"):
        f = Fraction(t)
        assert a.frame_at(float(f)) == int((f * exact) % 30)


def test_frame_fraction_fps_exact():
    a = Animation(3, Fraction(10, 3))  # 每帧 0.3 秒
    assert a.frame_at(Fraction(0)) == 0
    assert a.frame_at(Fraction(3, 10)) == 1
    assert a.frame_at(Fraction(9, 10)) == 0  # 0.9s = 3 帧槽，回绕


# --------------------------------------------------------------------- #
# 大时间戳不丢精度
# --------------------------------------------------------------------- #
def test_frame_huge_timestamp_no_precision_loss():
    a = Animation(4, 10.0)
    # 1e12 秒：槽位 1e13，模 4 = 0（float 槽位域取模，不丢整数精度）
    assert a.frame_at(1e12) == 0
    assert a.frame_at(10 ** 12) == 0
    # 精确路径（int/Fraction）保证 1e12 + 0.1s 精确落到帧 1
    assert a.frame_at(10 ** 12) == 0
    assert a.frame_at(Fraction(10 ** 12) + Fraction(1, 10)) == 1
    # float 的 1e12+0.1 按 IEEE754 舍入到其最近可表示值，结果须确定、在界内
    fv = a.frame_at(1e12 + 0.1)
    assert 0 <= fv < 4
    assert fv == a.frame_at(1e12 + 0.1)
    # 不循环时大时间戳停末帧
    assert a.frame_at(1e12, loop=False) == 3


def test_frame_huge_timestamp_exact_boundaries():
    a = Animation(5, 2.5)  # 每帧 0.4 秒，周期 2 秒
    for k in range(1, 50):
        t = Fraction(k) * 2  # 整数个周期
        assert a.frame_at(t) == 0
        assert a.frame_at(float(t)) == 0
        assert a.frame_at(t + Fraction(2, 5)) == 1


# --------------------------------------------------------------------- #
# 可变帧时长
# --------------------------------------------------------------------- #
def test_frame_variable_durations():
    # 帧时长 1/10、2/10、3/10、4/10 秒，周期 1.0 秒（用 Fraction 给精确边界）
    a = Animation(4, None, durations=[Fraction(1, 10), Fraction(2, 10),
                                      Fraction(3, 10), Fraction(4, 10)])
    assert a.frame_at(0.0) == 0
    assert a.frame_at(Fraction(99, 1000)) == 0
    assert a.frame_at(Fraction(1, 10)) == 1   # 边界归下一帧
    assert a.frame_at(0.25) == 1
    assert a.frame_at(Fraction(3, 10)) == 2   # 0.1+0.2
    assert a.frame_at(Fraction(6, 10)) == 3   # 0.1+0.2+0.3
    assert a.frame_at(Fraction(999, 1000)) == 3
    assert a.frame_at(1.0) == 0               # 整周期回绕
    assert a.frame_at(Fraction(11, 10)) == 1
    # float 输入按其二进制精确值定位：0.3 的实际值略小于 0.1+0.2，仍在帧 1
    assert a.frame_at(0.3) == 1
    assert a.frame_at(0.1) == 1


def test_frame_variable_durations_no_loop():
    a = Animation(3, None, durations=[0.5, 0.25, 0.25])
    assert a.frame_at(0.99, loop=False) == 2
    assert a.frame_at(1.0, loop=False) == 2
    assert a.frame_at(50.0, loop=False) == 2


def test_frame_variable_durations_fraction_inputs():
    a = Animation(2, None, durations=[Fraction(1, 3), Fraction(2, 3)])
    assert a.frame_at(Fraction(1, 3)) == 1
    assert a.frame_at(Fraction(2, 3)) == 1
    assert a.frame_at(Fraction(1)) == 0


# --------------------------------------------------------------------- #
# ping-pong 往返播放
# --------------------------------------------------------------------- #
def test_frame_pingpong_constant():
    a = Animation(4, 10.0)
    # 用精确时间戳表达帧槽边界，避免浮点取整歧义
    expected = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1]
    got = [a.frame_at(Fraction(i, 10), pingpong=True) for i in range(len(expected))]
    assert got == expected


def test_frame_pingpong_constructor_default():
    a = Animation(4, 10.0, pingpong=True)
    assert a.frame_at(Fraction(4, 10)) == 2
    assert a.frame_at(Fraction(6, 10)) == 0
    # 逐次覆盖可关闭
    assert a.frame_at(Fraction(4, 10), pingpong=False) == 0


def test_frame_pingpong_no_loop():
    a = Animation(4, 10.0)
    # 关闭循环时 ping-pong 与普通模式一样停末帧
    assert a.frame_at(1.0, loop=False, pingpong=True) == 3


def test_frame_pingpong_variable_durations():
    # 帧时长 0.1/0.2/0.3，bounds=[.1,.3,.6]，周期 0.6；starts=[0,.1,.3]
    a = Animation(3, None, durations=[Fraction(1, 10), Fraction(2, 10),
                                      Fraction(3, 10)])
    pp = dict(pingpong=True)
    # 正向段
    assert a.frame_at(Fraction(0), **pp) == 0
    assert a.frame_at(Fraction(1, 10), **pp) == 1
    assert a.frame_at(Fraction(3, 10), **pp) == 2
    assert a.frame_at(Fraction(6, 10), **pp) == 2    # 精确端点停末帧
    # 反向段：距末端点 d，帧 i 区间 [starts[i], starts[i+1])
    # 0.61 -> d=0.59 落在 [.3,.6) 仍为帧 2
    assert a.frame_at(Fraction(61, 100), **pp) == 2
    # 0.79 -> d=0.41 仍在 [.3,.6) 帧 2；0.8 -> d=0.4 同样帧 2
    assert a.frame_at(Fraction(79, 100), **pp) == 2
    assert a.frame_at(Fraction(8, 10), **pp) == 2
    # 0.9 -> d=0.3 是帧 2 反向区间下界，仍为帧 2；0.91 -> d=.29 进入帧 1
    assert a.frame_at(Fraction(9, 10), **pp) == 2
    assert a.frame_at(Fraction(91, 100), **pp) == 1
    assert a.frame_at(Fraction(11, 10), **pp) == 1   # d=.1 是帧 1 下界
    # 1.19 -> d=.01 在 [0,.1) 帧 0；1.2 精确回到起点；1.21 仅越过起点 .01s 仍帧 0
    assert a.frame_at(Fraction(119, 100), **pp) == 0
    assert a.frame_at(Fraction(12, 10), **pp) == 0
    assert a.frame_at(Fraction(121, 100), **pp) == 0
    # 1.3 越过下一周期起点 0.1s，重新正向进入帧 1
    assert a.frame_at(Fraction(13, 10), **pp) == 1


def test_frame_single_frame_animation():
    a = Animation(1, 10.0)
    for t in (0.0, 0.5, 1e12):
        assert a.frame_at(t) == 0
        assert a.frame_at(t, pingpong=True) == 0


# --------------------------------------------------------------------- #
# 可区分的错误
# --------------------------------------------------------------------- #
def test_frame_distinguishable_errors():
    with pytest.raises(FrameCountError):
        Animation(0, 10.0)
    with pytest.raises(FrameCountError):
        Animation(-2, 10.0)

    with pytest.raises(FrameRateError):
        Animation(4, 0.0)
    with pytest.raises(FrameRateError):
        Animation(4, -1.0)
    with pytest.raises(FrameRateError):
        Animation(4, float("nan"))

    with pytest.raises(NegativeTimeError):
        make_frame_animation().frame_at(-0.1)
    with pytest.raises(NegativeTimeError):
        make_frame_animation().frame_at(-10 ** 12)

    with pytest.raises(InvalidTimeError):
        make_frame_animation().frame_at(float("nan"))
    with pytest.raises(InvalidTimeError):
        make_frame_animation().frame_at(float("inf"))

    with pytest.raises(DurationError):
        Animation(3, None, durations=[0.1, 0.2, 0.0])
    with pytest.raises(DurationError):
        Animation(3, None, durations=[0.1, -0.2, 0.3])
    with pytest.raises(DurationError):
        Animation(3, None, durations=[0.1, 0.2])  # 长度不匹配

    # 所有错误仍可被 ValueError 捕获（兼容既有行为）
    for fn in (
        lambda: Animation(0, 10.0),
        lambda: Animation(4, 0.0),
        lambda: make_frame_animation().frame_at(-1.0),
    ):
        with pytest.raises(ValueError):
            fn()


def test_frame_error_types_are_distinct():
    assert not issubclass(FrameCountError, FrameRateError)
    assert not issubclass(NegativeTimeError, FrameCountError)
    assert issubclass(NegativeTimeError, ValueError)
    assert issubclass(DurationError, ValueError)


# --------------------------------------------------------------------- #
# 并发安全
# --------------------------------------------------------------------- #
def test_frame_concurrent_access():
    a = make_frame_animation()
    errors = []
    results = [[] for _ in range(8)]

    def worker(idx):
        try:
            for i in range(5000):
                t = (i % 400) * 0.01
                f = a.frame_at(t)
                assert 0 <= f < 4
                results[idx].append(f)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert not errors
    expected = [a.frame_at((i % 400) * 0.01) for i in range(5000)]
    assert all(r == expected for r in results)


# --------------------------------------------------------------------- #
# 性能：10 万次取帧 < 100 ms
# --------------------------------------------------------------------- #
def test_frame_performance_100k():
    import time

    a = Animation(8, 30.0)
    ts = [((i * 37) % 1000) * 0.001 for i in range(100_000)]
    a.frame_at(0.123)  # 预热
    start = time.perf_counter()
    for t in ts:
        f = a.frame_at(t)
        assert 0 <= f < 8
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100.0, f"10 万次取帧耗时 {elapsed_ms:.1f} ms"


def test_frame_variable_performance_100k():
    import time

    a = Animation(8, None, durations=[0.05, 0.1, 0.15, 0.2, 0.05, 0.1, 0.15, 0.2])
    ts = [((i * 37) % 1000) * 0.001 for i in range(100_000)]
    a.frame_at(0.123)
    start = time.perf_counter()
    for t in ts:
        f = a.frame_at(t)
        assert 0 <= f < 8
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100.0, f"10 万次可变时长取帧耗时 {elapsed_ms:.1f} ms"
