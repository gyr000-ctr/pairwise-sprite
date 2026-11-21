"""sprite 核心 API：精灵动画帧选择。

特性
----
- 固定 fps 或逐帧可变时长（``durations``）。
- 普通循环、关闭循环（停在末帧）与 ping-pong 往返播放。
- 取帧完全基于参数的纯函数：无内部可变状态，天然并发安全。
- ``int`` / :class:`~fractions.Fraction` / 数字字符串走精确有理运算，
  ``1e12`` 秒级时间戳不丢精度；``float`` 输入保持浮点语义
  （``floor(t*fps)``），与历史行为一致。

公开异常均可相互区分，且均继承自 :class:`ValueError`，因此既有代码中
``except ValueError`` 的行为保持不变。
"""

import math
from fractions import Fraction

__all__ = [
    "Animation",
    "AnimationError",
    "FrameCountError",
    "FrameRateError",
    "DurationError",
    "TimeError",
    "NegativeTimeError",
    "InvalidTimeError",
]


class AnimationError(ValueError):
    """sprite 动画相关错误的基类（仍是 ``ValueError``）。"""


class FrameCountError(AnimationError):
    """帧数为 0、负数或非正整数。"""


class FrameRateError(AnimationError):
    """fps 为 0、负数、NaN/Inf 或类型非法。"""


class DurationError(AnimationError):
    """帧时长为 0、负数、NaN/Inf、数量不匹配或类型非法。"""


class TimeError(AnimationError):
    """时间参数相关错误基类。"""


class NegativeTimeError(TimeError):
    """时间戳为负数（可与其他错误区分）。"""


class InvalidTimeError(TimeError):
    """时间戳为 NaN、Inf 或类型非法。"""


def _gcd_list(values):
    g = 0
    for v in values:
        g = math.gcd(g, v)
    return g or 1


def _lcm(a, b):
    return a // math.gcd(a, b) * b


class Animation:
    """一次构造、反复取帧的动画描述。

    Parameters
    ----------
    frames:
        正整数帧数。
    fps:
        每秒帧数（可为非整数浮点，如 ``29.97``）。提供 ``durations`` 时
        可为 ``None``。
    durations:
        可选的逐帧时长序列（秒）。给出后按各帧自身时长累加选帧，
        ``fps`` 仅做合法性校验、不参与取帧。
    pingpong:
        默认播放方向策略；``frame_at`` 可逐次覆盖。
    """

    def __init__(self, frames, fps, durations=None, *, pingpong=False):
        if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
            raise FrameCountError("frames 必须是正整数，收到 %r" % (frames,))
        self._frames = frames
        self._pingpong_default = bool(pingpong)

        # ---- 可变帧时长 -------------------------------------------------
        if durations is not None:
            durations = list(durations)
            if len(durations) != frames:
                raise DurationError(
                    "durations 长度 %d 与帧数 %d 不一致" % (len(durations), frames)
                )
            ratios = [self._rational(d, DurationError, "帧时长") for d in durations]
            for num, _den in ratios:
                if num <= 0:
                    raise DurationError("帧时长必须为正数")
            # 公共“滴答”单位：tick = 1 / unit 秒，所有帧边界都落在整数 tick 上。
            unit = 1
            for num, den in ratios:
                unit = _lcm(unit, den)
            ticks = [num * (unit // den) for num, den in ratios]
            g = _gcd_list(ticks)
            if g > 1:  # 约分，缩小整数规模
                unit //= g
                ticks = [v // g for v in ticks]
            self._unit = unit
            self._ticks = ticks
            self._cycle_ticks = sum(ticks)
            # 累计边界 bounds[i] = 第 i 帧结束处的滴答数（单调递增）。
            bounds = []
            acc = 0
            for v in ticks:
                acc += v
                bounds.append(acc)
            self._bounds = bounds
            # 反向播放的起始边界表：starts[i] = 帧 i 反向区间的下界。
            self._starts = [0] + bounds[:-1]
            self._variable = True
        else:
            self._variable = False
            self._unit = 0
            self._ticks = None
            self._cycle_ticks = 0
            self._bounds = None
            self._starts = None

        # ---- fps 校验（固定帧率路径实际使用；可变时长路径仍要求合法） ----
        if fps is None and durations is not None:
            self._fps_num = self._fps_den = 0
            self._fps_float = 0.0
        else:
            fr = self._rational(fps, FrameRateError, "fps")
            if fr[0] <= 0:
                raise FrameRateError("fps 必须为正数，收到 %r" % (fps,))
            self._fps_num, self._fps_den = fr
            self._fps_float = float(fps)

    # ------------------------------------------------------------------ #
    # 入参解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _rational(value, exc_cls, what):
        """把输入转换为最简 (num, den) 整数元组；非法值抛 ``exc_cls``。"""
        if isinstance(value, bool):
            raise exc_cls("%s 不接受布尔值" % what)
        if isinstance(value, int):
            num, den = value, 1
        elif isinstance(value, Fraction):
            num, den = value.numerator, value.denominator
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise exc_cls("%s 必须是有限数值，收到 %r" % (what, value))
            num, den = value.as_integer_ratio()
        elif isinstance(value, str):
            try:
                value = Fraction(value)
            except (ValueError, ZeroDivisionError):
                raise exc_cls("%s 不是合法数值: %r" % (what, value))
            num, den = value.numerator, value.denominator
        else:
            raise exc_cls("%s 类型不支持: %r" % (what, type(value).__name__,))
        if den <= 0 or num == 0:
            raise exc_cls("%s 必须非零且为正" % what)
        g = math.gcd(abs(num), den)
        return num // g, den // g

    @staticmethod
    def _validate_float_time(t):
        if math.isnan(t):
            raise InvalidTimeError("时间不能是 NaN")
        if math.isinf(t):
            raise InvalidTimeError("时间不能是无穷大")
        if t < 0.0 or (t == 0.0 and math.copysign(1.0, t) < 0.0):
            raise NegativeTimeError("时间不能为负数，收到 %r" % (t,))

    @staticmethod
    def _time_ratio(t):
        """非浮点时间戳 -> (num, den)；负数/坏类型抛可区分异常。"""
        if isinstance(t, bool):
            raise InvalidTimeError("时间不接受布尔值")
        if isinstance(t, int):
            num, den = t, 1
        elif isinstance(t, Fraction):
            num, den = t.numerator, t.denominator
        elif isinstance(t, str):
            try:
                f = Fraction(t)
            except (ValueError, ZeroDivisionError):
                raise InvalidTimeError("时间不是合法数值: %r" % (t,))
            num, den = f.numerator, f.denominator
        else:
            raise InvalidTimeError("时间类型不支持: %r" % (type(t).__name__,))
        if num < 0:
            raise NegativeTimeError("时间不能为负数，收到 %r" % (t,))
        return num, den

    # ------------------------------------------------------------------ #
    # 取帧（纯函数，无状态）
    # ------------------------------------------------------------------ #
    def frame_at(self, t, loop=True, pingpong=None):
        """返回时间 ``t``（秒）处的帧号，结果恒在 ``[0, frames)``。

        - ``loop=True``：按帧时长累加取模循环。
        - ``loop=False``：超出末帧边界后停在末帧。
        - ``pingpong=True``：到端点后反向（三角波折叠）。
        """
        if pingpong is None:
            pingpong = self._pingpong_default
        n = self._frames
        if n == 1:
            # 单帧动画任何输入都只有帧 0（仍需先校验时间合法性）。
            if isinstance(t, float):
                self._validate_float_time(t)
            else:
                self._time_ratio(t)
            return 0

        if isinstance(t, float):
            self._validate_float_time(t)
            if self._variable:
                # 可变时长：浮点转精确有理，边界按帧时长的精确累加判定，
                # 避免 0.1+0.2 类累计误差。
                num, den = t.as_integer_ratio()
                return self._frame_variable_exact(num, den, loop, pingpong)
            return self._frame_constant_float(t, loop, pingpong)

        num, den = self._time_ratio(t)
        if self._variable:
            return self._frame_variable_exact(num, den, loop, pingpong)
        return self._frame_constant_exact(num, den, loop, pingpong)

    # ---------------- float 路径（保持历史浮点语义） ------------------- #
    def _frame_constant_float(self, t, loop, pingpong):
        n = self._frames
        # 槽位直接在浮点域计算（与历史 floor(t*fps) 语义一致），
        # 回绕在整数槽位域取模，避免秒域周期除不尽产生的漂移。
        slot = math.floor(t * self._fps_float)
        if not loop:
            return min(slot, n - 1)
        if pingpong:
            return self._fold_pingpong(slot, n)
        return slot % n

    @staticmethod
    def _fold_pingpong(slot, n):
        period = 2 * (n - 1)
        folded = slot % period
        return min(folded, period - folded)

    # ---------------- 精确有理路径（int/Fraction/str） ----------------- #
    def _frame_constant_exact(self, num, den, loop, pingpong):
        slot_num = num * self._fps_num
        slot_den = den * self._fps_den
        n = self._frames

        if loop:
            q = slot_num // slot_den
            if pingpong:
                return self._fold_pingpong(q, n)
            return q % n

        last = n - 1  # 不循环：钳制到最后一个帧槽
        if slot_num >= last * slot_den:
            return last
        return slot_num // slot_den

    def _frame_variable_exact(self, num, den, loop, pingpong):
        # 绝对位置以“滴答”为单位但保留完整有理值 (p_num/den)，
        # tick = 1/unit 秒；全程整数跨乘比较，不丢帧内余数。
        p_num = num * self._unit          # 位置分子（分母仍为 den）
        cycle = self._cycle_ticks
        cycle_num = cycle * den

        if not loop:
            if p_num >= cycle_num:        # 超出末帧边界：停末帧
                return self._frames - 1
            return self._locate_forward(p_num, den)

        if pingpong:
            # 往返周期为 2*cycle，先在有理域折叠。
            period_num = 2 * cycle_num
            folded_num = p_num - (p_num // period_num) * period_num
            if folded_num < cycle_num:
                # 正向段：帧 i 占用 [bounds[i-1], bounds[i])。
                return self._locate_forward(folded_num, den)
            if folded_num == cycle_num:
                # 精确抵达末端点：停在末帧。
                return self._frames - 1
            # 反向段：距末端点距离 d = period - folded。反向时帧 i 对应
            # 距离区间 [starts[i], starts[i+1])，其中
            # starts = [0, bounds[0], ..., bounds[n-2]]。
            return self._locate_reverse(period_num - folded_num, den)

        phase_num = p_num - (p_num // cycle_num) * cycle_num
        return self._locate_forward(phase_num, den)

    def _locate_forward(self, pos_num, den):
        """有理滴答位置 -> 帧槽：帧 i 满足 ``bounds[i-1] <= pos < bounds[i]``，
        即满足 ``pos < bounds[i]`` 的第一个 i；整数跨乘，无浮点参与。"""
        bounds = self._bounds
        lo, hi = 0, self._frames
        while lo < hi:
            mid = (lo + hi) // 2
            if pos_num < bounds[mid] * den:
                hi = mid
            else:
                lo = mid + 1
        if lo >= self._frames:
            return self._frames - 1
        return lo

    def _locate_reverse(self, dist_num, den):
        """反向距离 -> 帧槽：帧 i 满足 ``starts[i] <= dist < starts[i+1]``，
        即对起始边界表 starts 做 bisect_right 后减一。整数跨乘，无浮点。"""
        starts = self._starts
        lo, hi = 0, self._frames
        while lo < hi:
            mid = (lo + hi) // 2
            if starts[mid] * den <= dist_num:
                lo = mid + 1  # starts[mid] <= dist，继续向右找
            else:
                hi = mid
        idx = lo - 1
        if idx < 0:
            return 0
        if idx >= self._frames:
            return self._frames - 1
        return idx
