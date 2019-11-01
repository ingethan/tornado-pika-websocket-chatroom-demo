#!/usr/bin/env python
# -*- coding:utf-8 -*-
import asyncio
import aiohttp
import random


speaker = ['诸葛亮', '张昭', '虞翻', '步骘', '薛综', '陆绩', '程秉', '严畯']


async def fetch(url, data):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as resp:
            res = await resp.text()
            print(res)


async def main():
    tasks = []
    for i in range(1, 500):
        tasks.append(fetch('http://localhost:5000/', data=dict(nickname=random.choice(speaker), msg=f'-- {i} --')))
    await asyncio.wait(tasks)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
