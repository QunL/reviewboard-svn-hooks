reviewboard-svn-hooks
=====================

Base on reviewboard-svn-hooks-0.2.1-r20, add some new features, such as: support multi-repository.

* Support multi-repositories. Every repository define itself configure file about reviewboard server , username/password, shipit count, expert group etc.
* 

Usage：
* Download the python file, and make svn hook have read and execute right.
* Set the config file , such as the repository 's hook dir. 
[reviewboard svn hooks configure file](https://github.com/QunL/reviewboard-svn-hooks/wiki/reviewboard-svn-hooks-configure-file)
* In pre-commit script, call the strict_check.py
REPOS="$1"
TXN="$2"
/path/to/strict_review.py  $REPOS $TXN /path/to/reviewboardsvnhook.conf
exit $?
