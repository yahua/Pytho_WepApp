import asyncio, logging
import aiomysql

def log(sql, args=()):
    logging.info('SQL: %s' % sql)

async def create_pool(db, password, user, loop, minsize=1, maxsize=10, autocommit=True, charset='utf8', port=3306,
                      host='localhost', **kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        charset=charset,
        autocommit=autocommit,
        maxsize=maxsize,
        minsize=minsize,
        loop=loop
    )

async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    async with __pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?', '%s'), args or ())
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()
            logging.info('rows returned: %s', len(rs))
            return rs


async def execute(sql, args, autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected


class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name;
        self.column_type = column_type;
        self.primary_key = primary_key;
        self.default = default;

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)

class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        #排除Model类本身
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)

        # 获取table名称:
        tableName = attrs.get('__table__', None) or name
        logging.info('found model:%s (table:%s)'% (name, tableName))

        #获取所有的Field和主键名
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            #需要封装过的类型，才能解析，  可否使用的系统的类型？？
            if isinstance(v, Field):
                logging.info('found mapping: %s ==> %s', k, v)
                mappings[k] = v
                if v.primary_key:
                    # 找到主键
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s', k)
                    primaryKey = k
                else:
                    fields.append(k)

        if not primaryKey:
            raise RuntimeError('Primary key not found')

        for k in mappings.keys():
            attrs.pop(k)
        # 转化位字符串
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))

        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (
        tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (
        tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)

class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % item)

    def __setattr__(self, key, value):
        self[key]= value

    def getValue(self, key):
        return getattr(self, key)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod  #类方法
    async def find (cls, pk):
        ' find object by primary key. '
        s1 = cls.__select__
        s2 = cls.__primary_key__
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]
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
            if isinstance(limit, int):
                sql.append('?')
                sql.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                sql.append(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = self.getValue(self.__primary_key__)
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)

#测试
class User(Model):
    __table__ = 'user'

    id = IntegerField(primary_key=True)
    name = StringField()

async def test(loop=None):
    await create_pool('ceshi', '123456', 'root', loop)

    #查找
    #user = await User.find(1)
    #list = await User.findAll()
    #print('user: %s', list)
    #count = await User.findNumber('id')
    #print('count: %s', count)

    #插入
    #user = User(id=4, name='小白')
    #await user.save()

    #更新

    # user = await User.find(1)
    # user.name = '小黑'
    # await user.update()

    #删除
    # user = await User.find(2)
    # await user.remove()


loop = asyncio.get_event_loop()
loop.run_until_complete(test())
loop.run_forever()
