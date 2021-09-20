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
"""Miscellaneous utility functions used throughout the modules."""
from __future__ import annotations

import collections
import functools
import html
import importlib.resources as imr
import itertools
import math
import operator
import os
import pathlib
import re
import typing as t

import lxml.html
import markupsafe
from lxml import etree
from PIL import ImageFont

import capellambse

ATT_XT = f'{{{capellambse.NAMESPACES["xsi"]}}}type'
FALLBACK_FONT = "OpenSans-Regular.ttf"
RE_TAG_NS = re.compile(r"(?:\{(?P<ns>[^}]*)\})?(?P<tag>.*)")
LINEBREAK_AFTER = frozenset({"br", "p", "ul", "li"})
TABS_BEFORE = frozenset({"li"})

_T = t.TypeVar("_T")


def flatten_html_string(text: str) -> str:
    """Convert an HTML-string to plain text."""
    frags = lxml.html.fragments_fromstring(text)
    if not frags:
        return ""

    text_container: t.List[str] = []
    if isinstance(frags[0], str):
        text_container.append(frags.pop(0))

    for frag in frags:
        text_container.extend(_flatten_subtree(frag))

    return "".join(text_container).rstrip()


def _flatten_subtree(element: etree._Element) -> t.Iterator[str]:
    def remove_whitespace(text: str):
        return re.sub("[\n\t]", "", text).lstrip()

    if element.tag in TABS_BEFORE:
        yield "             • "

    if element.text:
        yield remove_whitespace(element.text)

    for child in element:
        yield from _flatten_subtree(child)

    if element.tag in LINEBREAK_AFTER:
        yield "\n"

    if element.tail:
        yield remove_whitespace(element.tail)


# File name and path manipulation
def normalize_pure_path(
    path: t.Union[pathlib.PurePosixPath, str],
    *,
    base: t.Union[pathlib.PurePosixPath, str] = "/",
) -> pathlib.PurePosixPath:
    """Make a PurePosixPath relative to ``/`` and collapse ``..`` components.

    Parameters
    ----------
    path
        The input path to normalize.
    base
        The base directory to which relative paths should be
        interpreted.  Ignored if the input path is not relative.

    Returns
    -------
    path
        The normalized path.
    """
    path = pathlib.PurePosixPath("/", base, path)

    parts: t.List[str] = []
    for i in path.parts[1:]:
        if i == "..":
            try:
                parts.pop()
            except IndexError:
                pass
        else:
            parts.append(i)

    return pathlib.PurePosixPath(*parts)


# Text processing and rendering
@functools.lru_cache(maxsize=8)
def load_font(fonttype: str, size: int) -> ImageFont.FreeTypeFont:
    for name in (fonttype, fonttype.upper(), fonttype.lower()):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass

    with imr.open_binary("capellambse", FALLBACK_FONT) as fallback_font:
        return ImageFont.truetype(fallback_font, size)


@functools.lru_cache(maxsize=256)
def extent_func(
    text: str,
    fonttype: str = "segoeui.ttf",
    size: int = 8,
) -> t.Tuple[float, float]:
    """Calculate the display size of the given text.

    Parameters
    ----------
    text
        Text to calculate pixel size on
    fonttype
        The font type / face
    size
        Font size (px)

    Returns
    -------
    width
        The calculated width of the text (px).
    height
        The calculated height of the text (px).
    """
    width = height = 0
    font = load_font(fonttype, size)
    (width, height), _ = font.font.getsize(text)
    return (width * 10 / 7, height * 10 / 7)


def get_text_extent(
    text: str,
    width: t.Union[float, int] = math.inf,
) -> t.Tuple[float, float]:
    """Calculate the bounding box size of ``text`` after line wrapping.

    Parameters
    ----------
    text
        Text to calculate the size for.
    width
        Maximum line length (px).

    Returns
    -------
    width
        The width of the text after word wrapping (px).
    height
        The height of the text after word wrapping (px).
    """
    lines = [*map(extent_func, word_wrap(text, width))]
    line_height = max(l[1] for l in lines)
    return max(l[0] for l in lines), line_height * len(lines)


def ssvparse(
    string: str,
    cast: t.Callable[[str], _T],
    *,
    parens: t.Sequence[str] = ("", ""),
    sep: str = ",",
    num: int = 0,
) -> t.Sequence[_T]:
    """Parse a string of ``sep``-separated values wrapped in ``parens``.

    Parameters
    ----------
    string
        The input string.
    cast
        A type to cast the values into.
    parens
        The parentheses that must exist around the input.  Either a
        two-character string or a 2-tuple of strings.
    sep
        The separator between values.
    num
        If non-zero, only accept exactly this many values.

    Returns
    -------
    values
        List of values cast into given type.

    Raises
    ------
    ValueError
        *   If the parentheses are missing around the input string.
        *   If the expected number of values doesn't match the actual
            number.
    """
    if not string.startswith(parens[0]) or not string.endswith(parens[1]):
        raise ValueError(f"Missing {parens} around string: {string}")
    string = string[len(parens[0]) : -len(parens[1])]
    values = [cast(v) for v in string.split(sep)]
    if num and len(values) != num:
        raise ValueError(
            f"Expected {num} values, found {len(values)}: {string}"
        )
    return values


def word_wrap(text: str, width: t.Union[float, int]) -> t.Sequence[str]:
    """Perform word wrapping for proportional fonts.

    Whitespace at the beginning of input lines is preserved, but other
    whitespace is collapsed to single spaces.

    Parameters
    ----------
    text
        The text to wrap.
    width
        The width in pixels to wrap to.

    Returns
    -------
    lines
        A list of strings, one for each line, after wrapping.
    """

    def rejoin(
        words: t.Iterable[str], start: int, stop: t.Optional[int]
    ) -> str:
        return " ".join(itertools.islice(words, start, stop))

    def splitline(line: str) -> t.List[str]:
        match = re.search(r"^\s*", line)
        assert match is not None
        words = line.split()

        if words:
            words[0] = match.group(0) + words[0]
        return words

    output_lines = []
    input_lines = collections.deque(text.splitlines())
    while input_lines:
        words = collections.deque(splitline(input_lines.popleft()))
        if not words:
            output_lines.append("")
            continue

        words_count = len(words)
        while (
            extent_func(rejoin(words, 0, words_count))[0] > width
            and words_count > 0
        ):
            words_count -= 1

        if words_count > 0:
            output_lines.append(rejoin(words, 0, words_count))
            if words_count < len(words):
                input_lines.appendleft(rejoin(words, words_count, None))

        else:
            word = words.popleft()
            letters_count = len(word)
            while (
                extent_func(word[:letters_count])[0] > width
                and letters_count > 1
            ):
                letters_count -= 1

            output_lines.append(word[:letters_count])
            if letters_count < len(word):
                words.appendleft(word[letters_count:])

            input_lines.appendleft(" ".join(words))

    return output_lines or [""]


# XML tree modification and navigation
def fragment_link(cur_frag: t.Union[str, os.PathLike], href: str) -> str:
    """Combine current fragment and ``href`` into an absolute link.

    Parameters
    ----------
    cur_frag
        The source fragment file, relative to the project's root AIRD
        file.
    href
        The target element's ID, or a Capella-style link.

    Returns
    -------
    link
        Full reference link for given fragment.
    """
    if isinstance(cur_frag, os.PathLike):
        cur_frag = cur_frag.__fspath__()
    assert isinstance(cur_frag, str)

    if href.startswith("#"):
        return cur_frag + href
    if "#" in href:
        href = href.split()[-1]  # Strip the type information, if any
        cur_frag = os.path.dirname(cur_frag)  # Strip old filename
        while href.startswith("../"):
            cur_frag = os.path.dirname(cur_frag)
            href = href[3:]
        return os.path.join(cur_frag, href)
    return f"{cur_frag}#{href}"


def repair_html(markup: str) -> str:
    """Try to repair broken HTML markup to prevent parse errors.

    Parameters
    ----------
    markup
        The markup to try and repair.

    Returns
    -------
    markup
        The repaired markup.
    """
    nodes: t.List[
        t.Union[str, lxml.html._Element]
    ] = lxml.html.fragments_fromstring(markup)
    if nodes and isinstance(nodes[0], str):
        firstnode: str = markupsafe.escape(nodes.pop(0))
    else:
        firstnode = ""
    assert all(isinstance(i, etree._Element) for i in nodes)

    for node in itertools.chain.from_iterable(
        map(operator.methodcaller("iter"), nodes)
    ):
        for k in list(node.keys()):
            if ":" in k:
                del node.attrib[k]

    othernodes = b"".join(
        etree.tostring(i, encoding="utf-8") for i in nodes
    ).decode("utf-8")

    return firstnode + othernodes


def resolve_namespace(tag: str) -> str:
    """Resolve a ':'-delimited symbolic namespace to its canonical form.

    Parameters
    ----------
    tag
        Symbolic namespace delimited by ':'.

    Returns
    -------
    tag
        Tag string in canonical form.
    """
    if ":" in tag:
        namespace, tag = tag.split(":")
        return f"{{{capellambse.NAMESPACES[namespace]}}}{tag}"
    return tag


def unescape_linked_text(
    loader: capellambse.loader.MelodyLoader, attr_text: t.Optional[str]
) -> markupsafe.Markup:
    """Transform the ``linkedText`` into regular HTML."""

    def flatten_element(
        elm: t.Union[lxml.html.HTMLElement, str]
    ) -> t.Iterator[str]:
        if isinstance(elm, str):
            yield html.escape(elm)
        elif elm.tag == "a":
            href = elm.get("href")
            if href is None:
                yield "&lt;broken link&gt;"
                yield html.escape(elm.tail or "")
                return
            if "#" in href:
                ehref = html.escape(href.rsplit("#", maxsplit=1)[-1])
            else:
                ehref = html.escape("#" + href)

            try:
                target = loader[href]
            except KeyError:
                yield f"&lt;deleted element {ehref}&gt;"
            else:
                if name := target.get("name"):
                    name = html.escape(name)
                else:
                    name = f"&lt;unnamed element {ehref}&gt;"
                yield f'<a href="{ehref}">{name}</a>'
            yield html.escape(elm.tail or "")
        else:
            yield html.escape(elm.text or "")
            for child in elm:
                yield from flatten_element(child)
            yield html.escape(elm.tail or "")

    elements = lxml.html.fragments_fromstring(attr_text or "")
    escaped_text = "".join(
        itertools.chain.from_iterable(flatten_element(i) for i in elements)
    )
    return markupsafe.Markup(escaped_text)


@t.overload
def xpath_fetch_unique(
    xpath: t.Union[str, etree.XPath],
    tree: etree._Element,
    elm_name: str,
    elm_uid: str = None,
    *,
    optional: t.Literal[False] = ...,
) -> etree._Element:
    ...


@t.overload
def xpath_fetch_unique(
    xpath: t.Union[str, etree.XPath],
    tree: etree._Element,
    elm_name: str,
    elm_uid: str = None,
    *,
    optional: t.Literal[True],
) -> t.Optional[etree._Element]:
    ...


def xpath_fetch_unique(
    xpath: t.Union[str, etree.XPath],
    tree: etree._Element,
    elm_name: str,
    elm_uid: str = None,
    *,
    optional: bool = False,
) -> t.Optional[etree._Element]:
    """Fetch an XPath result from the tree, ensuring that it's unique.

    Parameters
    ----------
    xpath
        The :class:`lxml.etree.XPath` object to apply, or an XPath
        expression as str.
    tree
        The (sub-)tree to which the XPath will be applied.
    elm_name
        A human-readable element name for error messages.
    elm_uid
        UID of the element which triggered this lookup.  Will be
        included in the error message if an error occured.
    optional
        True to return None in case the element is not found.  Otherwise
        a ValueError will be raised.

    Returns
    -------
    element
        The Element found by given ``xpath``.

    Raises
    ------
    ValueError
        *   If more than one element was found matching the ``xpath``.
        *   If ``optional`` is ``False`` and no element was found
            matching the ``xpath``.
    """
    if isinstance(xpath, str):
        xpath = etree.XPath(
            xpath, namespaces=capellambse.NAMESPACES, smart_strings=False
        )

    result = xpath(tree)
    if len(result) > 1:
        raise ValueError(
            f"Invalid XML: {elm_name!r} is not unique, found {len(result)}"
            + (f" while processing element {elm_uid!r}" if elm_uid else "")
        )
    if not optional and not result:
        raise ValueError(
            f"Invalid XML: {elm_name!r} not found"
            + (f" while processing element {elm_uid!r}" if elm_uid else "")
        )

    return result[0] if result else None


def xtype_of(
    elem: etree._Element,
) -> t.Optional[str]:
    """Return the ``xsi:type`` of the element.

    If the element has an ``xsi:type`` attribute, its value is returned.

    If the element does not have an ``xsi:type``, this function resolves
    the tag's namespace to the symbolic name and reconstructs the type
    with the ``namespace:tag`` template.

    Parameters
    ----------
    elem
        The :class:`lxml.etree._Element` object to return the
        ``xsi:type`` for.

    Returns
    -------
    xtype
        The ``xsi:type`` string of the provided element or ``None`` if
        the type could not be determined.
    """
    xtype = elem.get(ATT_XT)
    if xtype:
        return xtype

    tagmatch = RE_TAG_NS.fullmatch(elem.tag)
    assert tagmatch is not None
    ns = tagmatch.group("ns")
    tag = tagmatch.group("tag")
    if not ns:
        return None
    symbolic_ns = list(
        capellambse.yield_key_and_version_from_namespaces_by_plugin(ns)
    )
    if not symbolic_ns:
        raise ValueError(f"Unknown namespace {ns!r}")

    if len(symbolic_ns) > 1:
        raise ValueError(f"Ambiguous namespace {ns!r}: {symbolic_ns}")

    plugin_name, plugin_version = symbolic_ns[0][0], symbolic_ns[0][1]
    if not capellambse.check_plugin_version(plugin_name, plugin_version):
        raise ValueError(f"Not handled version {ns!r}")

    return f"{plugin_name}:{tag}"


# More iteration tools
def ntuples(
    num: int,
    iterable: t.Iterable[_T],
    *,
    pad: bool = False,
) -> t.Iterator[t.Tuple[_T, ...]]:
    r"""Yield N items of ``iterable`` at once.

    Parameters
    ----------
    num
        The number of items to yield at once.
    iterable
        An iterable.
    pad
        If the items in ``iterable`` are not evenly divisible by ``n``,
        pad the last yielded tuple with ``None``\ s.  If False, the last
        tuple will be discarded.

    Yields
    ------
    items
        A ``num`` long tuple of items from ``iterable``.
    """
    iterable = iter(iterable)
    while True:
        value = tuple(itertools.islice(iterable, num))
        if len(value) == num:
            yield value
        elif value and pad:
            yield value + (None,) * (num - len(value))
        else:
            break


# Simple one-trick helper classes
class EverythingContainer(t.Container[t.Any]):
    """A container that contains everything."""

    def __contains__(self, _: t.Any) -> bool:  # pragma: no cover
        """Return ``True``.

        Parameters
        ----------
        _
            Ignored.

        Returns
        -------
        is_contained
            Always ``True``.
        """
        return True


def get_transformation(
    class_: str,
    pos: t.Tuple[float, float],
    size: t.Tuple[float, float],
) -> t.Dict[str, str]:
    """
    Calculate transformation for class.

    The Scaling factor .725, translation constants (6, 5) are arbitrarily
    chosen to fit. Currently only ChoicePseudoState is tranformed.

    Parameteres
    -----------
    class_
        Classtype string
    pos
        Position-vector
    size
        Size vector
    """
    tranformation = dict(
        ChoicePseudoState="translate({tx},{ty}) scale({s}) rotate(45,{rx},{ry})",
    )
    if class_ not in tranformation:
        return {}

    s = 0.725
    tx, ty = (1 - s) * pos[0] + 6, (1 - s) * pos[1] + 5
    rx, ry = pos[0] + size[0] / 2, pos[1] + size[1] / 2
    return dict(
        transform=tranformation[class_].format(tx=tx, ty=ty, s=s, rx=rx, ry=ry)
    )