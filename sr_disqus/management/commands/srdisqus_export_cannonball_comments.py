#coding=utf-8
#
# This fork of `disqus_export` (from django-disqus) uses the official
# `disqus-python` Python bindings
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
import time
from optparse import make_option
from pprint import pformat
from pytz import utc, timezone

from cannonball.comments.models import Comment
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import NoArgsCommand, CommandError
from django.utils.encoding import smart_str

from disqusapi import DisqusAPI, APIError

DISQUS_SECRET_KEY = getattr(settings, 'DISQUS_SECRET_KEY', None)
DISQUS_PUBLIC_KEY = getattr(settings, 'DISQUS_PUBLIC_KEY', None)
DISQUS_ACCESS_TOKEN = getattr(settings, 'DISQUS_ACCESS_TOKEN', None)
DISQUS_WEBSITE_SHORTNAME = getattr(settings, 'DISQUS_WEBSITE_SHORTNAME', None)

LOCAL_TZ = timezone(getattr(settings, 'TIME_ZONE', 'America/Los_Angeles'))

LOCAL_IP_ADDRESSES = frozenset([
    '127.0.0.1',
    '10.8.0.1',
    '10.8.0.2',
    '10.8.0.3',
    '10.8.0.92',
    '10.8.0.93'
])


def dt_to_utc(naive_dt):
    local_dt = LOCAL_TZ.localize(naive_dt)
    return local_dt.astimezone(utc)


class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option('-d', '--dry-run', action="store_true", dest="dry_run",
                    help='Does not export any comments, but merely outputs' +
                         'the comments which would have been exported.'),
        make_option('-s', '--state-file', action="store", dest="state_file",
                    help="Saves the state of the export in the given file " +
                         "and auto-resumes from this file if possible."),
        make_option('-n', '--num', action="store", dest="limit", default=None,
                    help="The number of comments to export during this run."),
    )
    help = 'Export comments from contrib.comments to DISQUS'
    requires_model_validation = False

    #####

    def _get_comments_to_export(self, last_export_id=None, limit=None):
        """Return comments which should be exported."""
        qs = Comment.objects.filter(site=settings.SITE_ID).order_by('pk')
        if last_export_id is not None:
            print "Resuming after comment %s" % str(last_export_id)
            qs = qs.filter(id__gt=last_export_id)
        return qs[:limit]

    #####

    def _get_last_state(self, state_file):
        """Checks the given path for the last exported comment's id"""
        state = None
        fp = open(state_file)
        try:
            state = int(fp.read())
            print "Found previous state: %d" % (state,)
        finally:
            fp.close()
        return state

    def _save_state(self, state_file, last_pk):
        """Saves the last_pk into the given state_file"""
        fp = open(state_file, 'w+')
        try:
            fp.write(str(last_pk))
        finally:
            fp.close()

    #####

    def handle(self, **options):
        current_site = Site.objects.get_current()
        verbosity = int(options.get('verbosity'))
        dry_run = bool(options.get('dry_run'))
        state_file = options.get('state_file')
        limit = options.get('limit')
        last_exported_id = None

        thread_idents = {}
        thread_urls = {}

        #client = DisqusAPI(DISQUS_SECRET_KEY, DISQUS_PUBLIC_KEY)
        s_client = DisqusAPI(DISQUS_SECRET_KEY)

        if state_file is not None and os.path.exists(state_file):
            last_exported_id = self._get_last_state(state_file)

        comment_set = self._get_comments_to_export(last_exported_id, limit)
        comments_count = comment_set.count()
        if verbosity >= 1:
            print "Exporting %d comment(s)" % comments_count

        # if this is a dry run, we output the comments and exit
        if dry_run:
            print comment_set
            return
        # if no comments were found we also exit
        if not comments_count:
            return

        # Get a list of all forums for an API key. Each API key can have
        # multiple forums associated. This application only supports the one
        # set in the DISQUS_WEBSITE_SHORTNAME variable
        try:
            forum_data = s_client.forums.details(forum=DISQUS_WEBSITE_SHORTNAME)
            del forum_data
        except APIError:
            raise CommandError("Could not find forum '%s'. " % \
                                   DISQUS_WEBSITE_SHORTNAME +
                               "Please check your " +
                               "'DISQUS_WEBSITE_SHORTNAME' setting.")

        for comment in comment_set:
            if comment.content_object:
                if verbosity >= 1:
                    print "Exporting comment '%s'" % comment
                    print "\t", comment.content_object

                # Try to find a thread with the comments URL.
                url = 'http://%s%s' % (
                    current_site.domain,
                    comment.content_object.get_absolute_url()
                )

                thread_ident = "%s.%s-%s" % (
                    comment.content_object._meta.app_label,
                    comment.content_object._meta.object_name,
                    comment.content_object.id
                )
                if verbosity >= 1:
                    print "\t", url
                    print "\t", thread_ident

                thread_id = thread_urls.get(url, None)
                if not thread_id:
                    try:
                        thread = s_client.threads.details(
                            access_token=DISQUS_ACCESS_TOKEN,
                            thread="ident:%s" % thread_ident,
                            forum=DISQUS_WEBSITE_SHORTNAME
                        )
                        thread_id = thread['id']
                        thread_idents[thread_ident] = thread['id']
                        thread_urls[url] = thread['id']
                    except:
                        thread = None
                        thread_id = None

                if not thread_id:
                    try:
                        thread = s_client.threads.details(
                            access_token=DISQUS_ACCESS_TOKEN,
                            thread="link:%s" % url,
                            forum=DISQUS_WEBSITE_SHORTNAME
                        )
                        thread_id = thread['id']
                        thread_idents[thread_ident] = thread['id']
                        thread_urls[url] = thread['id']
                    except:
                        thread = None
                        thread_id = None

                # if no thread with the URL could be found, we create a new one.
                # to do this, we first need to create the thread and then
                # update the thread with a URL.
                if not thread_id:
                    thread = s_client.threads.create(
                        access_token=DISQUS_ACCESS_TOKEN,
                        forum=DISQUS_WEBSITE_SHORTNAME,
                        identifier=thread_ident,
                        url=url,
                        title=smart_str(comment.obj_title) or \
                            smart_str(comment.content_object),
                    )
                    thread_id = thread['id']
                    thread_idents[thread_ident] = thread['id']
                    thread_urls[url] = thread['id']

                # name and email are optional in contrib.comments but required
                # in DISQUS. If they are not set, dummy values will be used
                comment_state = 'approved'
                if (not comment.is_public) or (comment.is_removed):
                    comment_state = 'killed'
                ip_str = comment.ip_address
                if comment.ip_address in LOCAL_IP_ADDRESSES:
                    ip_str = '127.0.0.1'

                post_create_args = dict(
                    thread=thread_id,
                    message=smart_str(comment.comment),
                    author_name=smart_str(comment.userinfo.get('name',
                                                     'nobody')),
                    author_email=smart_str(comment.userinfo.get('email',
                                                      'nobody@example.org')),
                    author_url=smart_str(comment.userinfo.get('url', '')),
                    state=comment_state,
                    date=time.mktime(dt_to_utc(comment.submit_date).timetuple())
                )
                if ip_str:
                    post_create_args['ip_address'] = ip_str

                if verbosity >= 1:
                    print "\t", pformat(post_create_args)
                s_client.posts.create(**post_create_args)
            else:
                # comment likely belongs to a content_type that we
                # got rid of.
                continue
            if state_file is not None:
                self._save_state(state_file, comment.pk)
