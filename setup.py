#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='cannonball-disqus',
    version='0.1',
    description='Export cannonball.comments (django.contrib.comments) '+
        'into Disqus.',
    author='Mike Tigas',
    author_email='mike@tig.as',
    install_requires=['django', 'disqus-python',],
    url='http://github.com/SpokesmanReview/cannonball-disqus/',
    license='New BSD License',
    classifiers=[
      'Framework :: Django',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: BSD License',
      'Programming Language :: Python',
    ],
    include_package_data=True,
    packages=find_packages(),
    zip_safe=False,
)
