#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'James Z'

' url handlers '

import re, time, json, logging, hashlib, base64, asyncio

from www.coroweb import get, post

from www.models import User, Comment, Blog, next_id

@asyncio.coroutine
@get('/')
def index():
    users = yield from User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }