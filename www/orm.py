#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'James Z'

import asyncio,logging

import aiomysql

def log(sql, args=()):
    logging.info('SQL:%s' % sql)

# 在3.5中用async/await机制实现@asyncio.coroutine/yield from的功能
# 会出现很多意想不到的错误，例如此处创建连接池进行插入的时候

# 创建全局连接池，好处是不必频繁的打开和关闭数据库连接
# 每个HTTP请求都可以从连接池中直接获取数据库连接
@asyncio.coroutine
def create_pool(loop,**kw):
    log('create database connection pool……')
    global __pool
    # 调用一个子协程来创建全局连接池，create_pool返回一个pool实例对象
    __pool= yield from aiomysql.create_pool(
        # 连接的基本属性设置
        host=kw.get('host', 'localhost'), # 数据库服务器位置，本地
        port=kw.get('port', 3306), # MySQL端口号
        user=kw['user'], # 登录用户名
        password=kw['password'], # 登录密码
        db=kw['db'], # 数据库名
        charset=kw.get('charset','utf8'), # 设置连接使用的编码格式utf-8
        autocommit=kw.get('autocommit',True),  # 是否自动提交，默认false

        # 以下是可选项设置
        maxsize=kw.get('maxsize',10), # 最大连接池大小，默认10
        minsize=kw.get('minsize',1), # 最小连接池大小，默认1
        loop=loop # 设置消息循环
    )
@asyncio.coroutine
def select(sql, args, size=None):
    log(sql,args)
    global __pool
    with (yield from __pool) as conn:  # with...as...的作用就是try...exception...
        # 打开一个DictCursor，以dict形式返回结果的游标
        cur = yield from conn.cursor(aiomysql.DictCursor)
        # sql的占位符为? 而MySQL的占位符为%s 替换
        yield from cur.execute(sql.replace('?', '%s'), args or ())
        # 如果size不为空，则取一定量的结果集
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned:%s' % len(rs))
        return rs

# insert, update, delete通用函数
def execute(sql, args, autocommit=True):
    log(sql)
    with (yield from __pool) as conn:
        if not autocommit:
            yield from conn.begin()
        try:
            cur = yield from conn.cursor()
            yield from cur.execute(sql.replace('?','%s'), args)
            affected = cur.rowcount# execute()函数和select()函数所不同的是，cursor对象不返回结果集，而是通过rowcount返回结果数
            print('affected:',affected)
            yield from cur.close()
            if not autocommit:
                yield from conn.commit()
        except BaseException as e:
            if not autocommit:
                yield from conn.rollback()
            raise
        return affected

#这个函数在元类中被引用，作用是将其占位符拼接起来成'?,?,?'的形式
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    #比如说num=3，那L就是['?','?','?']，通过下面这句代码返回一个字符串'?,?,?'
    return ', '.join(L)

class Field(object):

    def __init__(self, name, column_type, primary_key, default):#default 默认值
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key#主键
        self.default = default

    # 返回类名(域名)，字段类型，字段名
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

# 字符串域。映射varchar
class StringField(Field):
    # ddl是数据定义语言("data definition languages")，默认值是'varchar(100)'，意思是可变字符串，长度为100
    # 和char相对应，char是固定长度，字符串长度不够会自动补齐，varchar则是多长就是多长，但最长不能超过规定长度
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

# 布尔域，映射boolean
class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

# 整型域，映射Integer
class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

# 浮点数域,映射float
class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

# 文本域
class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

# metaclass是类的模板，所以必须从`type`类型派生：
class ModelMetaclass(type):
    # __new__()方法接收到的参数依次是：
    #
    # 1.当前准备创建的类的对象；
    #
    # 2.类的名字；
    #
    # 3.类继承的父类集合；
    #
    # 4.类的方法集合。
    def __new__(cls, name, bases, attrs):
        #排除Model类本身
        if name=='Model':
            return type.__new__(cls, name, bases, attrs)
        #获取table名称
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        #获取主键名和所有field
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键:
                    if primaryKey:  # 在主键不为空的情况下又找到一个主键就会报错，因为主键有且仅有一个
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)

#当我们传入关键字参数metaclass时，它指示Python解释器在创建MyList时，要通过ListMetaclass.__new__()来创建。
class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    #__getattr__,使d.k可以访问
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    #d.k = v
    def __setattr__(self, key, value):
        self[key] = value

    #如果没有与key对应的的value，就返回None
    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod#这个装饰器是类方法的意思，这样就可以不创建实例直接调用类的方法
    @asyncio.coroutine
    def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
        sql = [cls.__select__]#'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            # 如果limit为一个整数n，那就将查询结果的前n个结果返回
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            # 如果limit为一个两个值的tuple，则前一个值代表索引，后一个值代表从这个索引开始要取的结果数
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)##用extend是为了把tuple的小括号去掉，因为args传参的时候不能包含tuple
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = yield from select(' '.join(sql), args)#sql语句和args都准备好了就交给select函数去执行
        return [cls(**r) for r in rs]#将所有查询结果返回

    @classmethod
    @asyncio.coroutine
    def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]#cls.__table__ = tablename
        if where:
            sql.append('where')
            sql.append(where)
        rs = yield from select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    # 按主键查找
    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        ' find object by primary key. '
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    # save、update、remove这三个方法需要管理员权限才能操作，所以不定义为类方法，需要创建实例之后才能调用

    @asyncio.coroutine
    def save(self):
        # 我们在定义__insert__时,将主键放在了末尾.因为属性与值要一一对应,因此通过append的方式将主键加在最后
        # 使用getValueOrDefault方法,可以调用time.time这样的函数来获取值
        print("start save")
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = yield from execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)
        else:
            print('save sucess!')

    @asyncio.coroutine
    def update(self):
        print('start update')
        # 像time.time,next_id之类的函数在插入的时候已经调用过了,没有其他需要实时更新的值,因此调用getValue
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)
        else:
            print('update sucess!')

    @asyncio.coroutine
    def remove(self):
        print('start remove')
        args = [self.getValue(self.__primary_key__)]
        rows = yield from execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
        else:
            print('remove sucess!')