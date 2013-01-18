#coding=utf-8
#
# Originally based on `disqus_export` (from django-disqus), but now just
# dumps WXR-flavored XML rather than directly use the Disqus API (which
# is generally impossible for large numbers of comments).
#
# Based on disqus/management/commands/disqus_export.py in
# https://github.com/arthurk/django-disqus
# Copyright (c) 2009-2011, Arthur Koziel
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#     * Neither the name of the author nor the names of other
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
import os.path
import cPickle as pickle
from itertools import takewhile, islice, count
from pytz import utc, timezone

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.management.base import NoArgsCommand
from django.template.loader import render_to_string
from django.utils.encoding import smart_str

from sr_disqus.utils import normalize_all
try:
    from cannonball.comments.models import Comment
except:
    # Your Mileage May Vary -- cannonball.comments is based on
    # pre-Django 1.0 django.contrib.comments
    from django.contrib.comments.models import Comment

LOCAL_TZ = timezone(getattr(settings, 'TIME_ZONE', 'America/Los_Angeles'))
CHUNK_SIZE = 2500

EXPORT_STATE_FILE = '/tmp/comments-data.dat'
EXPORT_FILENAME_FMT = '/tmp/comments-%03d.xml'  # %03d expands into file number


def dt_to_utc(naive_dt):
    """
    Based on Django `TIME_ZONE` setting (or the fallback string above in
    the `LOCAL_TZ` line), converts a naive datetime (from that TZ) into UTC.
    """
    local_dt = LOCAL_TZ.localize(naive_dt)
    return local_dt.astimezone(utc)


def chunk(stream, size):
    """
    Given an iterator `stream`, smaller iterators of `size` items. (Useful
    for partitioning absudrly large iterators into usable chunks for files
    or etc.)
    """
    return takewhile(bool, (list(islice(stream, size)) for _ in count()))


class Command(NoArgsCommand):
    help = 'Export comments from contrib.comments to WXR-flavored XML, ' +\
        'which is compatible with DISQUS import'
    requires_model_validation = False

    #####

    def _load_state_file(self):
        with open(EXPORT_STATE_FILE, 'rb') as f:
            self.state = pickle.load(f)

    def _save_state_file(self):
        with open(EXPORT_STATE_FILE, 'wb') as f:
            pickle.dump(self.state, f, -1)

    #####

    def _get_items_with_comments(self):
        # TODO: lol this code is probably entirely non-performant
        qs = Comment.objects.order_by('content_type__id', 'object_pk')
        qs = qs.distinct('content_type__id', 'object_pk')
        qs = qs.values_list('content_type__id', 'object_pk')

        ctypes_cache = {}
        for ctype_pk, obj_pk in qs.iterator():
            obj_pk = int(obj_pk)

            # skip if we've processed this before
            if (ctype_pk, obj_pk) in self.state['processed_items']:
                if self.verbosity > 1:
                    print "Skipped (ctype=%s, obj=%s); already processed" % (
                        ctype_pk, obj_pk)
                continue

            ctype = ctypes_cache.get(ctype_pk, None)
            if not ctype:
                ctype = ContentType.objects.get(id=ctype_pk)
                ctypes_cache[ctype_pk] = ctype

            try:
                i = ctype.get_object_for_this_type(id=obj_pk)
                yield i
            except KeyboardInterrupt:
                raise
            except:
                if self.verbosity > 1:
                    print "NOTE: %s(%s) does not exist" % (ctype.name, obj_pk)
                # item that this comment belongs to is no longer on our site
                continue

    def _get_comments_for_item(self, item):
        return Comment.objects.filter(
            content_type=ContentType.objects.get_for_model(item),
            object_pk=item.id
        ).order_by('submit_date')

    #####

    def handle(self, **options):
        self.current_site = Site.objects.get_current()
        self.verbosity = int(options.get('verbosity'))
        self.state = dict(processed_items=set(), last_chunk=None)

        if os.path.exists(EXPORT_STATE_FILE):
            try:
                self._load_state_file()
                if self.verbosity > 0:
                    print "loaded state file, %d items processed, %d files saved" % (
                        len(self.state['processed_items']),
                        int(self.state['last_chunk'])+1
                    )
            except KeyboardInterrupt:
                raise
            except:
                self.state = dict(processed_items=set(), last_chunk=None)
                if self.verbosity > 0:
                        print "NOTE: could not load state file"

        item_set = self._get_items_with_comments()

        if self.state['last_chunk'] != None:
            chunk_num = self.state['last_chunk']+1
        else:
            chunk_num = 0
        for items in chunk(item_set, CHUNK_SIZE):
            self.handle_chunk(items, chunk_num)

            self.state['last_chunk'] = chunk_num
            self._save_state_file()
            chunk_num += 1

    def handle_chunk(self, item_set, chunk_num):
        context = {
            'items': [],
            'site': self.current_site,

        }

        for item in item_set:
            if not item:
                continue
            if not ContentType.objects.get_for_model(item):
                continue

            # normalize property names across models that may have different
            # names for same thing (i.e. "title" vs "headline"). see utils.py.
            item = normalize_all(item)
            if item.__class__.__name__.lower() == "photo":
                setattr(item, 'title',
                    os.path.basename(smart_str(item.photo.name))
                )

            if not (
                getattr(item, 'title', None) or
                getattr(item, 'pubdate', None)
            ):
                continue
            try:
                item.get_absolute_url()
            except KeyboardInterrupt:
                raise
            except:
                continue

            # add `comments` property to item
            setattr(item, "comments", self._get_comments_for_item(item))

            # use "app.model(pk)" as disqus_id
            item_ctype = ContentType.objects.get_for_model(item)
            disqus_id = "%s.%s(%s)" % (
                item_ctype.app_label,
                item_ctype.name,
                item.pk
            )
            setattr(item, "disqus_id", disqus_id)

            # turn local timestmap into a UTC timestamp, since that's what
            # disqus wants on import
            setattr(item, 'gmt_timestamp', dt_to_utc(item.pubdate))

            if self.verbosity > 1:
                print "%s(%s) -> %s" % (item_ctype.name, item.pk, item.title)

            context['items'].append(item)

            self.state['processed_items'].add((item_ctype.pk, item.pk))

        with open(EXPORT_FILENAME_FMT % (chunk_num), 'wb') as f:
            f.write(
                smart_str(render_to_string("sr_disqus/wxr_base.xml", context))
            )
        if self.verbosity > 0:
            filename = EXPORT_FILENAME_FMT % chunk_num
            print "%s\t%s" % (filename, CHUNK_SIZE * (chunk_num + 1))
            print "=" * 60
