#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'James Z'

import www.orm
import asyncio,sys
from www.models import User, Blog, Comment

@asyncio.coroutine
def test(loop):
    yield from www.orm.create_pool(loop=loop, host='localhost', port=3306, user='root', password='177288', db='awesome')
    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
    yield from u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
loop.close()
if loop.is_closed():
    sys.exit(0)