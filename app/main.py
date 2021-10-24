from dotenv.main import load_dotenv
from flask import Flask, render_template, request
from flask_cors import CORS, cross_origin
from flask_socketio import SocketIO, send, emit
from lnd import Lnd
from google.protobuf.json_format import MessageToJson, MessageToDict
from dotenv import dotenv_values
import threading

config = dotenv_values(".env")

async_mode = None
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)
CORS(app)

lnd = Lnd('.', config['LNDHOST'])
# Dit moet om de een of andere reden anders crasht het
edge = lnd.get_edge(int(762491522716860417))

pubkeySubs = {}
channelSubs = {}

def channel_graph_worker():
    for response in lnd.get_channel_graph():
        if len(response.node_updates):
            for update in response.node_updates:
                if update.identity_key in pubkeySubs:
                    pubkeySubs[update.identity_key].add(request.sid)
                    node = lnd.get_node_channels(update.identity_key)
                    emit('pubkey', MessageToDict(node), json=True)
        if len(response.channel_updates):
            for update in response.channel_updates:
                if update.advertising_node in pubkeySubs:
                    channel = lnd.get_edge(int(update.chan_id))
                    for sid in pubkeySubs[update.advertising_node]:
                        socketio.emit('channel', MessageToDict(channel), room=sid)
                if update.connecting_node in pubkeySubs:
                    channel = lnd.get_edge(int(update.chan_id))
                    for sid in pubkeySubs[update.connecting_node]:
                        socketio.emit('channel', MessageToDict(channel), room=sid)
                if update.chan_id in channelSubs:
                    channel = lnd.get_edge(int(update.chan_id))
                    for sid in channelSubs[update.chanId]:
                        socketio.emit('channel', MessageToDict(channel), room=sid)

@app.route('/')
def index():
    return render_template('index.html',
                           sync_mode=socketio.async_mode)

@socketio.on('message')
def handle_message(data):
    print('received message: ' + data)

@socketio.on('subscribe_pubkey')
def handle_subscribe_pubkey(data):
    for pk in data['data']:
        node = lnd.get_node_channels(pk)
        if pk not in pubkeySubs:
            pubkeySubs[pk] = set()
        pubkeySubs[pk].add(request.sid)
        emit('pubkey', MessageToDict(node), json=True)

@socketio.on('subscribe_channel')
def handle_subscribe_channel(data):
    for channelId in data['data']:
        if channelId.isnumeric() and len(channelId) == 18:
            channel = lnd.get_edge(int(channelId))
            if channelId not in channelSubs:
                channelSubs[channelId] = set()
            channelSubs[channelId].add(request.sid)
            emit('channel', MessageToDict(channel), json=True)

@socketio.on('unsubscribe_pubkey')
def handle_unsubscribe_pubkey(data):
    if data['data'] in pubkeySubs: 
        pubkeySubs[data['data']].remove(request.sid)

@socketio.on('unsubscribe_channel')
def handle_unsubscribe_channel(data):
    if data['data'] in channelSubs: 
        channelSubs[data['data']].remove(request.sid)

@socketio.on('unsubscribe_all')
def handle_unsubscribe_all():
    for pubkey in pubkeySubs:
        pubkey.remove(request.sid)
    for channel in channelSubs:
        channel.remove(request.sid)

if __name__ == '__main__':
    t = threading.Thread(target=channel_graph_worker)
    t.start()
    socketio.run(app, host="0.0.0.0", debug=True)