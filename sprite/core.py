"""sprite 核心 API（初始未实现）。"""


class Animation:
    def __init__(self, frames, fps):
        """构造"""
        raise NotImplementedError

    def frame_at(self, t, loop=True):
        """取帧"""
        raise NotImplementedError
