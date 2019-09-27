#!/usr/bin/env python
# -*- coding:utf-8 -*-
from tornado.web import Application, RequestHandler
from tornado.websocket import WebSocketHandler
from tornado.ioloop import IOLoop
from pika import PlainCredentials, ConnectionParameters
from pika.adapters.tornado_connection import TornadoConnection
from pika.exceptions import ChannelClosed, ConnectionClosed
import time
import json
import os


BASE_PATH = os.path.dirname(__file__)

HOST = '127.0.0.1'
PORT = 5672
VHOST = '/'
USERNAME = 'guest'
PASSWORD = 'guest'
EXCHANGE = 'direct-exchange-A'
QUEUE = 'queue-py'
ROUTING_KEY = 'routing-key-to-queue-py'


class PikaClient:

    def __init__(self, io_loop):
        print(f'{self.__str__()}: __init__()')
        self.io_loop = io_loop
        self.connection = None
        self.connected = False
        self.channel = None

    # 打开链接
    def connect(self):
        if self.connected:
            return
        cred = PlainCredentials(USERNAME, PASSWORD)
        params = ConnectionParameters(host=HOST, port=PORT, virtual_host=VHOST, credentials=cred)
        self.connection = TornadoConnection(params, on_open_callback=self.on_connected)
        self.connection.add_on_close_callback(callback=self.on_closed)

    # 连接成功 callback
    def on_connected(self, connection):
        self.connected = True
        self.connection = connection
        print(f'{self.__str__()}: connected() succeed')
        self.connection.channel(on_open_callback=self.on_channel_open)

    # 关闭连接 callback
    def on_closed(self, connection):
        print(f'{self.__str__()}: on_closed()')
        connection.close()
        self.connection = None
        self.connected = False
        self.io_loop.stop()

    # 打开通道 callback
    def on_channel_open(self, channel):
        self.channel = channel
        self.channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
        # queue如果通过其他方式已经创建的话可能出错, 如果出错先删除再重新创建
        try:
            self.channel.queue_declare(queue=QUEUE, durable=True)
        except Exception as e:
            print(f'{self.__str__()} channel.queue_declare Error: ', e)
            channel.queue_delete(queue=QUEUE)
            channel.queue_declare(queue=QUEUE, durable=True)
        self.channel.queue_bind(queue=QUEUE, exchange=EXCHANGE, routing_key=ROUTING_KEY)
        # 如果是消费者, 绑定消息处理 callback
        if isinstance(self, Consumer):
            self.channel.basic_consume(queue=QUEUE, on_message_callback=self.handle_message, auto_ack=True)


# 消息消费者
class Consumer(PikaClient):

    def __init__(self, io_loop):
        super().__init__(io_loop)
        self.io_loop = io_loop
        self.listeners = set([])

    # 处理信息 callback
    def handle_message(self, channel, method, header, body):
        try:
            s = str(body, encoding='utf-8')
            msg = json.loads(s, encoding='utf-8', strict=False)
        except ValueError as e:
            print('ValueError:', e)
            msg = {}
        msg['time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        # 给每一个 WebSocket 链接者写入 msg
        for listener in self.listeners:
            listener.write_message(msg)

    # 增加WebSocket连接者
    def add_listener(self, listener):
        self.listeners.add(listener)
        print(f'{self.__str__()}: add_listener(listener), listener =', listener)

    # 移除WebSocket连接者
    def remove_listener(self, listener):
        try:
            self.listeners.remove(listener)
            print(f'{self.__str__()}: remove_listener(listener), listener =', listener)
        except KeyError:
            pass


# 消息发布者
class Publisher(PikaClient):

    def __init__(self, io_loop):
        super().__init__(io_loop)
        self.io_loop = io_loop

    # 发布信息
    def publish(self, msg):
        self.connect()
        try:
            print(f'{self.__str__()}.publish(msg), msg = ', msg)
            self.channel.basic_publish(exchange=EXCHANGE, routing_key=ROUTING_KEY, body=msg)
        except ConnectionClosed as e:
            print(f'{self.__str__()} start_publish ConnectionClosed Error: ', e)
            self.connect()
        except ChannelClosed as e:
            print(f'{self.__str__()} start_publish ChannelClosed Error: ', e)
            self.connect()
        except Exception as e:
            print(f'{self.__str__()} start_publish Exception Error: ', e)
            self.connect()


class ChatRoomHandler(RequestHandler):

    def get(self):
        self.render('webchat.html')

    # 多一个发布消息途径, 可有可无
    def post(self):
        data = {}
        try:
            s = str(self.request.body, encoding='utf-8')
            data = json.loads(s)
        finally:
            nickname = data.get('nickname', '匿名')
            msg = data.get('msg', 'this is a message')
            info = '{"nickname": "%s", "msg": "%s"}' % (nickname, msg)
            self.application.publisher.publish(info)
            self.write({
                'code': 200,
                'errMsg': 'ok'}
            )


class ChatWebSocketHandler(WebSocketHandler):

    # 连接建立: 将连接者添加到队列
    def open(self):
        print('WebSocket opened(self), self=', self)
        self.application.consumer.add_listener(self)

    # 发送消息: 调用publisher发布
    def on_message(self, message):
        self.application.publisher.publish(message)

    # 关闭连接: 将连接者从队列中移除
    def on_close(self):
        print('WebSocket closed(self), self=', self)
        self.application.consumer.remove_listener(self)

    # 允许websocket跨域
    def check_origin(self, origin):
        return True


handlers = [
    (r'/chat', ChatRoomHandler),
    (r'/ws', ChatWebSocketHandler),
]

app = Application(
    handlers,
    template_path=os.path.join(BASE_PATH, 'templates')
)


def main():
    io_loop = IOLoop.current()
    app.consumer = Consumer(io_loop)
    app.consumer.connect()
    app.publisher = Publisher(io_loop)
    app.publisher.connect()
    app.listen(8888)
    print(f'[ {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())} ] Run server http://127.0.0.1:8888')
    io_loop.start()


if __name__ == '__main__':
    main()
