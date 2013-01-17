"""
Due to legacy code, third-party code, and changing code styles, we have
models with different names for the same things. (i.e. "title" in one place,
"headline" in another.)

This file provides some methods for normalizing those names (and normalizing
`date` fields into `datetime` fields) on a per-item basis, by using `setattr`.
"""
from django.template.defaultfilters import striptags
from datetime import datetime, date, time

MIDNIGHT = time()


def normalize_datetimes(obj):
    """
    Cannonball irregularly uses date and datetime objects to represent pubdates because
    some models do not need time precision. This turns a questionable pubdate object into
    a datetime object by adding a midnight time to the date object.
    """
    if type(obj) is date:
        return datetime.combine(obj, MIDNIGHT)
    else:
        return obj


def normalize_pubdate_fields(item):
    """
    Ensures that the time has a pubdate attribute that's a datetime object.
    """
    if hasattr(item, 'pubdate'):
        if type(item.pubdate) is date:
            setattr(item, 'pubdate', datetime.combine(item.pubdate, MIDNIGHT))
    return item


def normalize_titles(item):
    """
    If the item does not have a title field, this creates one from the headline field
    or from the unicode representation of the item.
    """
    if hasattr(item, 'title'):
        return item

    if hasattr(item, 'headline'):
        setattr(item, 'title', item.headline)
    elif hasattr(item, 'name'):
        setattr(item, 'title', item.name)
    else:
        setattr(item, 'title', unicode(item))

    return item


def teaser_from_body(text, chars=350):
    """
    Creates a teaser from an extended body of text.
    """
    t = text.strip()
    if len(striptags(t)) < chars:
        return striptags(t)

    t = striptags(t[:chars] + t[chars:].split(". ", 1)[0].strip()).strip()
    #t = striptags(t[:chars] + t[chars:].split("</p>", 1)[0].strip()).strip()
    try:
        if t[-1] != '.':
            if t[-1] in ['!','?']:
                pass
            else:
                t += ". ..."
    except:
        pass

    return t


def normalize_teasers(item):
    """
    If the item does not have a teaser_text property, this creates one either based on
    the description property, or by shortening the body/story_text property.
    """
    if hasattr(item, 'teaser_text'):
        return item

    if hasattr(item, 'description'):
        setattr(item, 'teaser_text', item.description.strip())
    elif hasattr(item, 'body'):
        setattr(item, 'teaser_text', teaser_from_body(item.body))
    elif hasattr(item, 'story_text'):
        setattr(item, 'teaser_text', teaser_from_body(item.story_text))
    elif hasattr(item, 'post'):
        setattr(item, 'teaser_text', teaser_from_body(item.post))
    else:
        setattr(item, 'teaser_text', '')

    return item


def normalize_all(item):
    return normalize_titles(normalize_teasers(normalize_pubdate_fields(item)))

