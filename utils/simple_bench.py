#!/usr/bin/env python3
# Simple benchmark tool, requires X-Timer header in the response headers
import requests

BASE_URL = 'http://127.0.0.1:5500/'

PAGES = 10
PER_PAGE = 20


def do_time(url):
    r = requests.get(url)
    return float(r.headers['X-Timer'])


print('Warmup:', do_time(BASE_URL))
for i in range(1, PAGES + 1):
    page_url = BASE_URL + '?=' + str(i)

    page_times = [
        do_time(page_url) for _ in range(PER_PAGE)
    ]

    print('Page {:3d}: min:{:5.1f}ms max:{:5.1f}ms avg:{:5.1f}ms'.format(
        i,
        min(page_times) * 1000,
        max(page_times) * 1000,
        sum(page_times) / len(page_times) * 1000
    ))
