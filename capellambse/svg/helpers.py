# Copyright 2021 DB Netz AG
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import math
import typing as t

from capellambse import helpers


def check_for_horizontal_overflow(
    text: str,
    width: int | float,
    icon_padding: int | float,
    icon_size: int | float,
) -> t.Tuple[t.Sequence[str], float, float]:
    max_text_width = width - (icon_size + 2 * icon_padding)
    assert max_text_width >= 0
    lines = helpers.word_wrap(text, max_text_width)
    text_width = max(w for w, _ in map(helpers.extent_func, lines))
    label_width = text_width + icon_size + 2 * icon_padding
    assert text_width <= max_text_width
    assert label_width <= width
    label_margin = (width - label_width) / 2
    return (lines, label_margin, max_text_width)


def check_for_vertical_overflow(
    lines: t.Sequence[str],
    height: float | int,
    max_text_width: float | int,
) -> t.List[str]:
    overflow = ""
    lines_to_render = []
    text_height: t.Union[int, float] = 0
    for i, (line, (_, line_height)) in enumerate(
        zip(lines, map(helpers.extent_func, lines))
    ):
        if text_height + line_height > height:
            overflow = lines[i - 1] if i else line
            break

        text_height += line_height
        lines_to_render.append(line)

    if overflow:
        line_width = helpers.extent_func(overflow + "...")[0]
        if line_width < max_text_width:
            overflow += "..."
        else:
            dot_width = helpers.extent_func("...")[0]
            new_lines = helpers.word_wrap(
                overflow, math.floor(max_text_width - dot_width)
            )
            overflow = new_lines[0] + "..."

        if lines_to_render:
            lines_to_render[-1] = overflow
        else:
            lines_to_render.append(overflow)

    assert height >= text_height
    return lines_to_render