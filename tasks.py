#coding=utf8
from celery import Celery,platforms,group,chain
import time
import settings
import requests
import json
import datetime

import re
import random
from bs4 import BeautifulSoup
import redis
import logging
import logging.handlers
from redis.exceptions import WatchError
from settings import *
from db import db


celery = Celery('suited4you', broker='redis://localhost:6379/0', backend='redis://localhost')
celery.config_from_object('settings')


LOG_FILE = 'suited4you.log'
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024 * 50, backupCount=5)
fmt = '%(asctime)s - %(filename)s:%(lineno)s - %(name)s - %(message)s'
formatter = logging.Formatter(fmt)
handler.setFormatter(formatter)
logger = logging.getLogger('suited4you_log')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
# rd = settings.RD




@celery.task
def github_task(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2):
    try:
        for repo_owner, repo_name in [(repo_owner_1, repo_name_1), (repo_owner_2, repo_name_2)]:
            repo = gh.repos(repo_owner)(repo_name).get()
            repo_attr = [repo.watchers_count, repo.stargazers_count, repo.forks_count, repo.open_issues_count]
            repo_ctb = gh.repos(repo_owner)(repo_name).contributors().get()
            repo_ctb_count = len(repo_ctb)
            repo_lang = gh.repos(repo_owner)(repo_name).languages().get()
            # repo_lang = sorted(repo_lang.iteritems(), key=lambda x:x[1], reverse=True)
            # repo_lang = repo_lang[0][0]
            repo_ca = gh.repos(repo_owner)(repo_name).stats().commit_activity().get()
            ### mongo store
            coll = db.project
            one_repo = coll.find_one({"repo_owner": repo_owner, "repo_name": repo_name})
            if one_repo:
                one_repo['watchers_count'] = repo_attr[0]
                one_repo['stargazers_count'] = repo_attr[1]
                one_repo['forks_count'] = repo_attr[2]
                one_repo['open_issues'] = repo_attr[3]
                one_repo['repo_ctb_count'] = repo_ctb_count
                one_repo['language'] = repo_lang
                if repo_ca:
                    one_repo['commit_activity'] = repo_ca
                
                coll.save(one_repo)

    except Exception as ex:
        print ex
        return False
    return True


## always 429. why??
@celery.task
def reddit_task(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2):
    for key, value in [(repo_owner_1, repo_name_1), (repo_owner_2, repo_name_2)]:
        try:
            subscribers = reddit.get_sub_subscribers(key)
        except Exception as reddit_ex:
            print reddit_ex
            continue
        #mongo store
        coll = db.project
        one_reddit = coll.find_one({"repo_owner": key, "repo_name": value})
        if one_reddit:
            one_reddit['reddit_subscribers'] = subscribers
            coll.save(one_reddit)
        else:
            continue
    return True


@celery.task
def sof_task(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2):
    try:
        tags_infos = sof.get_tags_info([repo_name_1, repo_name_2])
    except Exception as sof_ex:
        print sof_ex
        return False
    #mongo store
    # print repo_owner_1, repo_name_1, repo_owner_2, repo_name_2
    coll = db.project
    one_sof = coll.find_one({"repo_owner": repo_owner_1, "repo_name": repo_name_1})
    if one_sof and repo_name_1 in tags_infos:
        one_sof['sof_count'] = tags_infos[repo_name_1]
        coll.save(one_sof)

    one_sof_2 = coll.find_one({"repo_owner": repo_owner_2, "repo_name": repo_name_2})

    if one_sof_2 and repo_name_2 in tags_infos:
        one_sof_2['sof_count'] = tags_infos[repo_name_2]
        coll.save(one_sof_2)
    
    return True


@celery.task
def diff_tasks(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2):
    try:
        repo_1 = gh.repos(repo_owner_1)(repo_name_1).get()
    except Exception as ex1:
        print ex1
        return 1
    try:
        repo_2 = gh.repos(repo_owner_2)(repo_name_2).get()
    except Exception as ex2:
        print ex2
        return 2
    for k, v in [(repo_owner_1, repo_name_1), (repo_owner_2, repo_name_2)]:
        coll = db.project
        repo = coll.find_one({"repo_owner": k, "repo_name": v})
        if not repo:
            coll.insert({"repo_owner": k, "repo_name": v})

    task_group = []
    github_s = github_task.s(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2)
    print 'github_s'
    sof_s = sof_task.s(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2)
    print 'sof_task'
    reddit_s = reddit_task.s(repo_owner_1, repo_name_1, repo_owner_2, repo_name_2)
    print 'reddit_task'
    task_group.append(github_s)
    task_group.append(sof_s)
    task_group.append(reddit_s)
    g1 = group(task_group)
    group_re = g1().get()
    
    return group_re


# ===========================================================================


# 查询一段时间内的fork的数量变化
# SELECT repository_forks, created_at
# FROM [githubarchive:github.timeline]
# WHERE 
#      repository_url = "https://github.com/celery/celery"
# ORDER BY created_at DESC

# 查询一段时间内的star的数量变化
# SELECT repository_watchers, created_at
# FROM [githubarchive:github.timeline]
# WHERE 
#      repository_url = "https://github.com/celery/celery"
# ORDER BY created_at DESC

# 查看issue的变化
# SELECT repository_open_issues, created_at
# FROM [githubarchive:github.timeline]
# WHERE 
#      repository_url = "https://github.com/celery/celery"
# ORDER BY created_at DESC

# ===========================================================================