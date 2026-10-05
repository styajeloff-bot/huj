from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from infrastructure.services.font_normalizer import (
    FontNormalizationError,
    normalize_font_to_woff2,
)


def _test_ttf(family_name: str = "Storefront Test") -> bytes:
    builder = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", "A"]
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({65: "A"})

    empty_pen = TTGlyphPen(None)
    a_pen = TTGlyphPen(None)
    a_pen.moveTo((100, 0))
    a_pen.lineTo((300, 700))
    a_pen.lineTo((500, 0))
    a_pen.closePath()
    builder.setupGlyf(
        {".notdef": empty_pen.glyph(), "A": a_pen.glyph()}
    )
    builder.setupHorizontalMetrics(dict.fromkeys(glyph_order, (600, 0)))
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": family_name,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"{family_name} Regular",
            "fullName": f"{family_name} Regular",
            "psName": f"{family_name.replace(' ', '')}-Regular",
        }
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
    )
    builder.setupPost()
    builder.setupMaxp()
    output = BytesIO()
    builder.save(output)
    return output.getvalue()


def _with_flavor(data: bytes, flavor: str) -> bytes:
    output = BytesIO()
    with TTFont(BytesIO(data), recalcTimestamp=False) as font:
        font.flavor = flavor
        font.save(output)
    return output.getvalue()


def _test_otf() -> bytes:
    builder = FontBuilder(1000, isTTF=False)
    glyph_order = [".notdef", "A"]
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({65: "A"})
    builder.setupHorizontalMetrics(dict.fromkeys(glyph_order, (600, 0)))
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "Storefront CFF Test",
            "styleName": "Regular",
            "uniqueFontIdentifier": "Storefront CFF Test Regular",
            "fullName": "Storefront CFF Test Regular",
            "psName": "StorefrontCFFTest-Regular",
        }
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
    )
    builder.setupPost()

    char_strings = {}
    empty_pen = T2CharStringPen(600, None)
    char_strings[".notdef"] = empty_pen.getCharString()
    a_pen = T2CharStringPen(600, None)
    a_pen.moveTo((100, 0))
    a_pen.lineTo((300, 700))
    a_pen.lineTo((500, 0))
    a_pen.closePath()
    char_strings["A"] = a_pen.getCharString()
    builder.setupCFF(
        "StorefrontCFFTest-Regular",
        {
            "FullName": "Storefront CFF Test Regular",
            "FamilyName": "Storefront CFF Test",
            "Weight": "Regular",
        },
        char_strings,
        {},
    )
    builder.setupMaxp()
    output = BytesIO()
    builder.save(output)
    return output.getvalue()


@pytest.mark.parametrize("source_flavor", [None, "woff", "woff2"])
async def test_normalizer_accepts_sfnt_woff_and_woff2(
    source_flavor: str | None,
) -> None:
    source = _test_ttf()
    if source_flavor is not None:
        source = _with_flavor(source, source_flavor)

    normalized = await normalize_font_to_woff2(source)

    assert normalized.startswith(b"wOF2")
    with TTFont(BytesIO(normalized)) as font:
        assert font.flavor == "woff2"
        assert font.getBestCmap() == {65: "A"}


async def test_normalizer_accepts_otf_cff() -> None:
    normalized = await normalize_font_to_woff2(_test_otf())

    assert normalized.startswith(b"wOF2")
    with TTFont(BytesIO(normalized)) as font:
        assert "CFF " in font


async def test_normalizer_rejects_non_font_bytes() -> None:
    with pytest.raises(FontNormalizationError):
        await normalize_font_to_woff2(b"not a font")
