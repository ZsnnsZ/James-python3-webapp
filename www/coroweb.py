#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'ZsnnsZ'

import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from www.apis import APIError

def get(path):# 装饰器的名称并接收参数，
    '''
    Define decorator @get('/path')
    在代码运行阶段为函数动态增强功能
    '''
    def decorator(func):# 次里层，若装饰器不需要参数那么次里层就可作为最外层
        @functools.wraps(func)#把原始函数的__name__等属性复制到wrapper()函数中，否则，有些依赖函数签名的代码执行就会出错。
        def wrapper(*args, **kw):# 最里层
            return func(*args, **kw)# 原函数
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

def post(path):
    '''
    Define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

# revise关键字参数&命名关键字参数
# *args是可变参数，args接收的是一个tuple；
# **kw是关键字参数，kw接收的是一个dict。
# 和关键字参数**kw不同，命名关键字参数需要一个特殊分隔符*，*后面的参数被视为命名关键字参数。

# 关于inspect.Parameter 的  kind 类型有5种：
# POSITIONAL_ONLY		只能是位置参数
# POSITIONAL_OR_KEYWORD	可以是位置参数也可以是关键字参数
# VAR_POSITIONAL		相当于是 *args
# KEYWORD_ONLY			关键字参数且提供了key
# VAR_KEYWORD			相当于是 **kw

# 获取没有默认值的命名关键字参数
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters# 获取fn的所有参数
    for name, param in params.items():# keyword_only命名(强制)关键字参数
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

# 获取fn的所有命名关键字参数
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

# 是否有命名关键字参数
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

# 获取关键字参数
def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

# 判断是否存在一个参数叫做request，并且该参数要在其他普通的位置参数之后
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        # 如果该参数既不是位置参数也不是命名关键字参数或关键字参数，抛异常
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
        return found

# 封装URL处理函数，从request中获取参数
class RequestHandler(object):

    def __init__(self, app ,fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        # 若有关键字参数或者命名关键字参数
        if self._has_var_kw_arg or self._has_named_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content_Type!')
                ct = request.content_type.lower()# content_type是request提交的消息主体类型
                if ct.startswith('application/json'):
                    params = yield from request.json()
                    if not isinstance(params,dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = yield from request.post()  # 浏览器表单信息用post方法来读取
                    kw = dict(**params)
                    # print('line 127'+kw)
                else:  # post的消息主体既不是json对象，又不是浏览器表单，那就只能返回不支持该消息主体类型
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)#request.match_info封装了与 request 的 path 和 method 完全匹配的 PlainResource 对象。
        else:
            # 没有关键字参数但是有命名关键字参数
            if not self._has_var_kw_arg and self._named_kw_args:
                copy = dict()
                # remove all unamed kw:
                for name in self._named_kw_args:#把命名关键字变量通过copy这个中间量存到kw中
                    if name in kw:
                        copy[name] = kw[name]# 大意写成copy['name'],这样就只给name赋了值，导致值缺失
                kw = copy
                print(kw)
            for k, v in request.match_info.items():#for 循环嵌套出了问题，发现之后我好伤心
                if k in kw:# 判断关键字参数和命名关键字参数是否有重复的
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    # return web.HTTPBadRequest('Missing argument: %s' % name)
                    print('coroweb.py 158')
        logging.info('call with args: %s' % str(kw))
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)

# 向app中添加静态文件目录
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))

# 把请求处理函数注册到app
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn))

# 将handlers模块中所有请求处理函数提取出来交给add_route去处理
def add_routes(app, module_name):
    # n = module_name.rfind('.')
    # if n == (-1):
    #     mod = __import__(module_name, globals(), locals())
    #     # __import__ 作用同import语句，但__import__是一个函数，并且只接收字符串作为参数,
    #     # 其实import语句就是调用这个函数进行导入工作的, 其返回值是对应导入模块的引用
    #     # __import__('os',globals(),locals(),['path','pip']) ,等价于from os import path, pip
    # else:
    #     name = module_name[n+1:]
    #     mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    mod = __import__(module_name, fromlist=[''])# 重构后
    for attr in dir(mod):# dir返回一个list
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)# fn.__method
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)