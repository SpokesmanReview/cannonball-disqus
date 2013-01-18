from django.core.cache import get_cache
from django.utils.encoding import smart_str
from django.template.defaultfilters import date as dateformat
from sr_disqus.serialization import encode_value, decode_value
import warnings
from django.core.cache import CacheKeyWarning


def get_locmem_cache():
    try:
        return get_cache('locmem')
    except:
        return get_cache('django.core.cache.backends.locmem.LocMemCache', **{
            'LOCATION': 'spokesman-locmem-fallback'
        })


def lc_get(key, default=None):
    loc_cache = get_locmem_cache()

    # Wrap in a catch_warnings/ignore block so that CacheKeyWarning is
    # ignored -- we're running this against locmem, never against memcached.
    warnings.simplefilter("ignore", CacheKeyWarning)
    try:
        val = decode_value(loc_cache.get(key), default)
    except:
        val = default
    warnings.simplefilter("default", CacheKeyWarning)
    return val


def lc_set(key, obj, timeout=None):
    loc_cache = get_locmem_cache()

    # Wrap in a catch_warnings/ignore block so that CacheKeyWarning is
    # ignored -- we're running this against locmem, never against memcached.
    warnings.simplefilter("ignore", CacheKeyWarning)
    try:
        val = loc_cache.set(key, encode_value(obj), timeout)
    except:
        pass
    warnings.simplefilter("default", CacheKeyWarning)
    return val

##############################################

def write_wxr_file(filename, site, items):
    with open(filename, 'wb') as fp:

        ##### Write header #####
        fp.write("""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:dsq="http://www.disqus.com/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:wp="http://wordpress.org/export/1.0/"
>
  <channel>""")

        for item in items:
            write_wxr_item(fp, site, item)

        ##### Write footer #####
        fp.write("""
  </channel>
</rss>""")

def write_wxr_item(fp, site, item):
    fp.write("""
    <item>
      <title>{item_title}</title>
      <link>http://{site_domain}{item_url}</link>
      <content:encoded><![CDATA[{teaser_text}]]></content:encoded>
      <dsq:thread_identifier>{disqus_id}</dsq:thread_identifier>
      <wp:post_date_gmt>{gmt_timestamp}</wp:post_date_gmt>
      <wp:comment_status>{comment_status}</wp:comment_status>""".format(**{
          'item_title': smart_str(item.title),
          'site_domain': smart_str(site.domain),
          'item_url': smart_str(item.get_absolute_url),
          'teaser_text': smart_str(item.teaser_text),
          'disqus_id': smart_str(item.disqus_id),
          'gmt_timestamp': smart_str(dateformat(item.gmt_timestamp, "Y-m-d H:i:s")),
          'comment_status': smart_str(item.comment_status),
      }))
    for comment in item.comments:
        write_xwr_itemcomment(fp, site, item, comment)
    fp.write("""
    </item>""")


def write_xwr_itemcomment(fp, site, item, comment):
    user_info = commentuser_info(comment.user_id, comment.user, comment.userinfo)

    comment_approved = 1
    if (not comment.is_public) or comment.is_removed:
        comment_approved = 0

    fp.write("""
      <wp:comment>
        <dsq:remote>
          <dsq:id>{user_id}</dsq:id>
          <dsq:avatar>{avatar}</dsq:avatar>
        </dsq:remote>
        <wp:comment_id>{comment_pk}</wp:comment_id>
        <wp:comment_author>{comment_author}</wp:comment_author>
        <wp:comment_author_email>{email}</wp:comment_author_email>
        <wp:comment_author_url>{url}</wp:comment_author_url>
        <wp:comment_author_IP>{ip_address}</wp:comment_author_IP>
        <wp:comment_date_gmt>{gmt_timestamp}</wp:comment_date_gmt>
        <wp:comment_content><![CDATA[{commentdata}]]></wp:comment_content>
        <wp:comment_approved>{approved}</wp:comment_approved>
        <wp:comment_parent>0</wp:comment_parent>
      </wp:comment>""".format(**{
          'user_id': smart_str(comment.user_id),
          'avatar': smart_str(user_info['avatar']),
          'comment_pk': smart_str(comment.pk),
          'comment_author': smart_str(user_info['display_name']),
          'url': smart_str(user_info['url']),
          'email': smart_str(user_info['email']),
          'ip_address': smart_str(comment.ip_address or "127.0.0.1"),
          'gmt_timestamp': smart_str(dateformat(comment.gmt_timestamp, "Y-m-d H:i:s")),
          'commentdata': smart_str(comment.bleached_comment),
          'approved': smart_str(comment_approved),
      }))



def commentuser_info(user_pk, user, userinfo):
    key = "userinfo(%s)" % user_pk
    info = lc_get(key, None)
    if info:
        return info

    info = {
        'avatar': '',
        'display_name': '',
        'email': '',
        'url': '',
    }
    try:
        if user and user.get_profile() and user.get_profile().avatar:
            info['avatar'] = user.get_profile().avatar.url
    except:
        pass

    try:
        if user and user.get_profile() and user.get_profile().display_name:
            info['display_name'] = user.get_profile().display_name
    except:
        pass
    if not info['display_name'] and userinfo['name']:
        info['display_name'] = userinfo['name']

    try:
        if user and user.get_profile() and user.get_profile().blog:
            info['url'] = user.get_profile().blog
    except:
        pass
    if not info['url'] and userinfo['url']:
        info['url'] = userinfo['url']

    if getattr(user, 'email', None):
        info['email'] = user.email
    elif userinfo.get('email', None):
        info['email'] = userinfo['email']

    lc_set(key, info)

    return info
