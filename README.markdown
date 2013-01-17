# cannonball-disqus

A `cannonball.comments` -> WXR XML exporter, for use with Disqus' WXR importer.
`cannonball.comments` is our [in-house][1] fork of a pre-Django 1.0
`django.contrib.comments`, so this code may or may not be useful to you.

[1]: http://www.spokesman.com/

## Requirements

* django
* pytz

## Usage

1. `pip install -e git://github.com/SpokesmanReview/cannonball-disqus.git`
2. Put `sr_disqus` in your `INSTALLED_APPS`
3. `django-admin.py srdisqus_export_cannonball_comments`
4. ???
5. profit
