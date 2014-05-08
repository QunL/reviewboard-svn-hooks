#!/usr/bin/python
# -*- coding:utf8 -*-
import os
import sys
import subprocess
import urllib2
import cookielib
import base64
import re
import shelve
import datetime
import ConfigParser
try:
    import json
except ImportError:
    import simplejson as json

from urlparse import urljoin

from utils import get_cmd_output, split

def get_os_temp_dir():
    import tempfile
    return tempfile.gettempdir()

def get_os_log_dir():
    platform = sys.platform
    if platform.startswith('win'):
        try:
            return os.environ['ALLUSERSPROFILE']
        except KeyError:
            print >>sys.stderr, 'Unspported operation system:%s'%platform
            sys.exit(1)
    return '/var/log'
DEBUG = False
def debug(s):
    if not DEBUG:
        return
    f = open(os.path.join(get_os_log_dir(), 'reviewboard-svn-hooks', 'debug.log'), 'at')
    print >>f, str(datetime.datetime.now()), s
    f.close()
class Conf(object):
""" Read the configuration file of reviewboard svn hook. """
    def read_conf_file(self, filename): 
        conf = ConfigParser.ConfigParser()

        if not conf.read(filename):
            raise StandardError('invalid configuration file:%s'%filename)

        self.COOKIE_FILE = conf.get('common', 'reviewboard_cookie_file')
        DEBUG = conf.getint('common', 'debug')
        self.REVIEWED_ID_DB_FILE = conf.get('common', 'reviewed_id_db_file')

        self.RB_SERVER = conf.get('reviewboard', 'url')
        self.USERNAME = conf.get('reviewboard', 'username')
        self.PASSWORD = conf.get('reviewboard', 'password')
        
        self.MIN_SHIP_IT_COUNT = conf.getint('rule', 'min_ship_it_count')
        self.MIN_EXPERT_SHIP_IT_COUNT = conf.getint('rule', 'min_expert_ship_it_count')
        experts = conf.get('rule', 'experts')
        self.EXPERTS = split(experts)
        review_path = conf.get('rule', 'review_path')
        self.REVIEW_PATH = split(review_path)
        ignore_path = conf.get('rule', 'ignore_path')
        self.IGNORE_PATH = split(ignore_path)
        

class SvnError(StandardError):
    pass

class Opener(object):
    def __init__(self, server, username, password, cookie_file = None):
        self._server = server
        if cookie_file is None:
            cookie_file = COOKIE_FILE
        self._auth = base64.b64encode(username + ':' + password)
        cookie_jar = cookielib.MozillaCookieJar(cookie_file)
        cookie_handler = urllib2.HTTPCookieProcessor(cookie_jar)
        self._opener = urllib2.build_opener(cookie_handler)

    def open(self, path, ext_headers, *a, **k):
        url = urljoin(self._server, path)
        debug("Opener open url:"+url)
        return self.abs_open(url, ext_headers, *a, **k)

    def abs_open(self, url, ext_headers, *a, **k):
        debug('url open:%s' % url)
        r = urllib2.Request(url)
        for k, v in ext_headers:
            r.add_header(k, v)
        r.add_header('Authorization', 'Basic ' + self._auth)
        try:
            rsp = self._opener.open(r)
            return rsp.read()
        except urllib2.URLError, e:
            raise SvnError(str(e))

def make_svnlook_cmd(directive, repos, txn):
    def get_svnlook():
        platform = sys.platform
        if platform.startswith('win'):
            return get_cmd_output(['where svnlook']).split('\n')[0].strip()
        return 'svnlook'

    cmd =[get_svnlook(), directive, '-t',  txn, repos]
    debug(cmd)
    return cmd

def get_review_id(repos, txn):
    svnlook = make_svnlook_cmd('log', repos, txn)
    log = get_cmd_output(svnlook)
    debug("get_review_id:"+log)
    rid = re.search(r'review:([0-9]+)', log, re.M | re.I)
    if rid:
        return rid.group(1)
    raise SvnError('No review id.')

def add_to_rid_db(rid, id_db_filename):
    USED_RID_DB = shelve.open(id_db_filename)
    if USED_RID_DB.has_key(rid):
        raise SvnError, "review-id(%s) is already used."%rid
    USED_RID_DB[rid] = rid
    USED_RID_DB.sync()
    USED_RID_DB.close()

def check_rb(repos, txn, conf):
    rid = get_review_id(repos, txn)
    path = 'api/review-requests/' + str(rid) + '/reviews/'
    opener = Opener(conf.RB_SERVER, conf.USERNAME, conf.PASSWORD)
    rsp = opener.open(path, {})
    reviews = json.loads(rsp)
    debug("check_rb get rsp:"+str(reviews))
    if reviews['stat'] != 'ok':
        raise SvnError, "get reviews error."
    ship_it_users = set()
    for item in reviews['reviews']:
        ship_it = int(item['ship_it'])
        if ship_it:
            ship_it_users.add(item['links']['user']['title'])
    
    if len(ship_it_users) < MIN_SHIP_IT_COUNT:
        raise SvnError, "not enough of ship_it."
    expert_count = 0
    for user in ship_it_users:
        if user in conf.EXPERTS:
            expert_count += 1
    if expert_count < conf.MIN_EXPERT_SHIP_IT_COUNT:
        raise SvnError, 'not enough of key user ship_it.'
    add_to_rid_db(rid, conf.REVIEWED_ID_DB_FILE)

def is_ignorable(changed, IGNORE_PATH):
    for line in changed.split('\n'):
        if not line.strip():
            continue
        f = line[4:]
        flg = False
        for ignore_path in IGNORE_PATH:
            if ignore_path in f:
                flg = True
                break
        if not flg:
            return False
    return True

def _main():
    debug('command:' + str(sys.argv))
    repos = sys.argv[1]
    txn = sys.argv[2]
    conf_filename = sys.argv[3]
    
    # read the configuration file.
    Conf conf;
    conf.read(conf_filename)

    svnlook = make_svnlook_cmd('changed', repos, txn)
    changed = get_cmd_output(svnlook)
    debug("main: "+changed)

    if is_ignorable(changed, conf.IGNORE_PATH):
        debug("All commit is ignorabled.")
        return

    if not conf.REVIEW_PATH:
        debug("not REVIEW_PATH return true")
        check_rb(repos, txn)
        return 

    for line in changed.split('\n'):
        f = line[4:]
        for review_path in REVIEW_PATH:
            if review_path in f:
                debug("Find ["+review_path +"] in line:"+f)
                check_rb(repos, txn)
                return

#def main():
if __name__ == '__main__':
    try:
        _main()
    except SvnError, e:
        debug("SvnError exception:"+str(e))
        print >> sys.stderr, str(e)
        exit(1)
    except Exception, e:
        debug("Exception:"+str(e))
        print >> sys.stderr, str(e)
        import traceback
        traceback.print_exc(file=sys.stderr)
        exit(1)
    else:
        exit(0)

