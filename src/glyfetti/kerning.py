"""Horizontal advance kerning from OpenType PairPos and legacy kern tables.

BMFont represents a single horizontal advance per pair, not contextual shaping.
https://learn.microsoft.com/en-us/typography/opentype/spec/gpos#lookup-type-2-pair-adjustment-positioning-subtable
"""
from collections import defaultdict
import warnings

from fontTools.ttLib import TTFont

MAX_PAIRS = 1_000_000


def _advance(record):
    first, second = getattr(record, 'Value1', None), getattr(record, 'Value2', None)
    unsupported = any(getattr(first, field, 0) for field in ('XPlacement', 'YPlacement', 'YAdvance'))
    unsupported |= any(getattr(second, field, 0) for field in ('XPlacement', 'YPlacement', 'XAdvance', 'YAdvance'))
    if unsupported:
        return None
    return getattr(first, 'XAdvance', 0)


def _subtables(lookup):
    for table in lookup.SubTable:
        kind = lookup.LookupType
        if kind == 9:
            kind, table = table.ExtensionLookupType, table.ExtSubTable
        if kind == 2:
            yield table


def _lookups(font, script):
    if 'GPOS' not in font:
        return []
    table = font['GPOS'].table
    if table.ScriptList is None or table.FeatureList is None or table.LookupList is None:
        return []
    scripts = {record.ScriptTag: record.Script for record in table.ScriptList.ScriptRecord}
    selected = scripts.get(script) or scripts.get('DFLT')
    if selected is None or selected.DefaultLangSys is None:
        return []
    language = selected.DefaultLangSys
    features = list(language.FeatureIndex)
    if language.ReqFeatureIndex != 0xFFFF:
        features.append(language.ReqFeatureIndex)
    indices = set()
    for index in features:
        feature = table.FeatureList.FeatureRecord[index]
        if feature.FeatureTag == 'kern':
            indices.update(feature.Feature.LookupListIndex)
    return [table.LookupList.Lookup[index] for index in sorted(indices)]


def _candidates(table, glyphs):
    covered = glyphs.intersection(table.Coverage.glyphs)
    if table.Format == 1:
        for first, pairs in zip(table.Coverage.glyphs, table.PairSet):
            if first in covered:
                for record in pairs.PairValueRecord:
                    if record.SecondGlyph in glyphs:
                        yield first, record.SecondGlyph
    elif table.Format == 2:
        second_classes = defaultdict(list)
        for second in sorted(glyphs):
            second_classes[table.ClassDef2.classDefs.get(second, 0)].append(second)
        for first in sorted(covered):
            row = table.Class1Record[table.ClassDef1.classDefs.get(first, 0)]
            for index, record in enumerate(row.Class2Record):
                if _advance(record) != 0:
                    for second in second_classes[index]:
                        yield first, second


def _match(table, first, second):
    if first not in table.Coverage.glyphs:
        return None
    if table.Format == 1:
        pairs = table.PairSet[table.Coverage.glyphs.index(first)]
        return next((record for record in pairs.PairValueRecord if record.SecondGlyph == second), None)
    if table.Format == 2:
        return table.Class1Record[table.ClassDef1.classDefs.get(first, 0)].Class2Record[table.ClassDef2.classDefs.get(second, 0)]
    return None


def _eligible(font, lookup, glyphs):
    """Respect lookup flags; ignored marks cannot form an adjacent BMFont pair."""
    if 'GDEF' not in font:
        return glyphs
    gdef = font['GDEF'].table
    classes = getattr(getattr(gdef, 'GlyphClassDef', None), 'classDefs', {})
    attachment = getattr(getattr(gdef, 'MarkAttachClassDef', None), 'classDefs', {})
    flags = lookup.LookupFlag
    mark_set = None
    if flags & 0x10:
        sets = getattr(gdef, 'MarkGlyphSetsDef', None)
        if sets is not None:
            mark_set = set(sets.Coverage[lookup.MarkFilteringSet].glyphs)
    result = set()
    for glyph in glyphs:
        kind = classes.get(glyph, 0)
        if kind and flags & (1 << kind):
            continue
        if kind == 3:
            if mark_set is not None and glyph not in mark_set:
                continue
            if mark_set is None and flags >> 8 and attachment.get(glyph, 0) != flags >> 8:
                continue
        result.add(glyph)
    return result


def read_kerning(path, chars, size, condense=1, variation=None, script='latn'):
    """Return BMFont-compatible integer pairs, limited to the exported characters."""
    with TTFont(path) as source:
        font = source
        if 'fvar' in font:
            from fontTools.varLib.instancer import instantiateVariableFont
            location = variation or {}
            if isinstance(location, list):
                location = dict(zip((axis.axisTag for axis in font['fvar'].axes), location))
            location = {axis.axisTag: location.get(axis.axisTag, axis.defaultValue) for axis in font['fvar'].axes}
            font = instantiateVariableFont(font, location, inplace=False)
        try:
            return _read(font, chars, size * condense / font['head'].unitsPerEm, script)
        finally:
            if font is not source:
                font.close()


def _read(font, chars, scale, script):
    cmap = font.getBestCmap() or {}
    characters = defaultdict(list)
    for char in sorted(set(chars)):
        if ord(char) in cmap:
            characters[cmap[ord(char)]].append(ord(char))
    glyphs = set(characters)
    lookups = _lookups(font, script)
    adjustments = defaultdict(int)
    unsupported = False
    if lookups:
        tables = [(list(_subtables(lookup)), _eligible(font, lookup, glyphs)) for lookup in lookups]
        candidates = set()
        for subtables, eligible in tables:
            for table in subtables:
                for pair in _candidates(table, eligible):
                    candidates.add(pair)
                    if len(candidates) > MAX_PAIRS:
                        raise ValueError('kerning: too many pairs; reduce chars or set kerning to false')
        for first, second in sorted(candidates):
            for subtables, eligible in tables:
                if first not in eligible or second not in eligible:
                    continue
                for table in subtables:
                    record = _match(table, first, second)
                    if record is not None:
                        value = _advance(record)
                        if value is None:
                            unsupported = True
                        else:
                            adjustments[first, second] += value
                        break  # Only the first matching subtable in a lookup applies.
    elif 'kern' in font:
        for table in font['kern'].kernTables:
            coverage = getattr(table, 'coverage', 0)
            if table.format != 0 or not coverage & 1 or coverage & 6:
                continue
            for pair, value in table.kernTable.items():
                if pair[0] in glyphs and pair[1] in glyphs:
                    if coverage & 8:
                        adjustments[pair] = value
                    else:
                        adjustments[pair] += value
    if unsupported:
        warnings.warn('Some kerning records require placement or second-glyph adjustments and cannot be represented in BMFont; those records were skipped.', stacklevel=3)
    result = []
    for (first, second), value in sorted(adjustments.items()):
        amount = round(value * scale)
        if amount:
            for left in characters[first]:
                for right in characters[second]:
                    result.append({'first': left, 'second': right, 'amount': amount})
                    if len(result) > MAX_PAIRS:
                        raise ValueError('kerning: too many pairs; reduce chars or set kerning to false')
    return sorted(result, key=lambda pair: (pair['first'], pair['second']))
