
'url handlers'
import re, time, json, logging, hashlib, base64, asyncio
from www.coroweb import get, post
from www.models import User, Comment, Blog, next_id
from www.apis import APIValuaError, APIResourceNotFoundError
from conf.config import configs

from aiohttp import web

COOKIE_NAME = 'awesome'
_COOKIE_KEY = configs['session']['secret']

def user2cookie(user, max_age):
    '''
       Generate cookie str by user.
       '''
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

@get('/')
def index(request):
    #users = await  User.findAll()
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time() - 120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time() - 3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time() - 7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }
@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

@get('/api/users')
async def get_all_users():
    users = await User.findAll()
    for u in users:
        u.passwd = '******'

    return dict(users=users)

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
@post('/api/users')
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValuaError('name')
    if not email or not email.strip():
        raise APIValuaError('email')
    if not passwd or not passwd.strip():
        raise APIValuaError('passwd')

    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIValuaError('', 'register failed, email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    #make session cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r