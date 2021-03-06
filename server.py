import socket
import threading
import videosocket
from config import *

class Server:
    def __init__(self, host='', port=50000):
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.host = host
        self.port = port
        self.buffer_size = 2048
        self.clients = dict()
        self._busy_clients = set()

    def _safe_recv(self, client):
        try:
            msg = client.recv(self.buffer_size)
            return msg
        except:
            return None

    def accept_conn(self):
        while True:
            client, client_addr = self.server.accept()
            print("Client with address: %s:%s has connected" %(client_addr))
            threading.Thread(target=self.handle_client, args=(client,)).start()

    def handle_client(self, client):
        while True:
            username = self._safe_recv(client).decode(ENCODING)
            if username in self.clients.keys():
                client.send(bytes("USERNAME_UNAVAILABLE", ENCODING))
            else:
                client.send(bytes("USERNAME_AVAILABLE", ENCODING))
                break
        vsock = videosocket.VideoSocket(client)
        self.clients[username] = (client, vsock)
        is_video = False
        receiver_username = None

        while True:
            if is_video:
                frame_bytes = vsock.vreceive()
                try:
                    if frame_bytes == 1:
                        is_video = False
                        self.send_to_one(receiver_username, bytes("-2", ENCODING))
                        self._busy_clients.remove(receiver_username)
                        self._busy_clients.remove(username)
                        continue
                    elif frame_bytes == 2:
                        is_video = False
                        continue
                except:
                    pass
                self.send_to_one(receiver_username, frame_bytes)

            else:
                msg = self._safe_recv(client)
                if msg is None:
                    break
                print(username + "-----" + msg.decode(ENCODING))
                if msg == bytes("QUIT", ENCODING):
                    client.close()
                    del self.clients[username]
                    self.broadcast(None, "Client %s has left the conversation" %(username))
                    break

                elif msg == bytes("READY_FOR_VIDEO_CALL", ENCODING):
                    is_video = True

                elif msg == bytes("VIDEO_CALL_INITIATE", ENCODING):
                    client.send(msg)

                elif msg == bytes("VIDEO_CALL_START", ENCODING):
                    # this client has initiated a video call
                    online_users = self.get_online_users(username)
                    client.send(online_users)

                    # receive the username client selected to chat with
                    receiver_username = self._safe_recv(client).decode(ENCODING)
                    if receiver_username == "VIDEO_CALL_ABORT":
                        continue
                    print("%s requested a video call to: %s" %(username, receiver_username))

                    # send video call request to receiving target
                    success = self.get_receiver_confirmation(client, username, receiver_username)

                    if success:
                        # send acceptance message to initiator
                        client.send(bytes("VIDEO_CALL_START", ENCODING))

                elif msg == bytes("VIDEO_CALL_REJECTED", ENCODING) or msg == bytes("VIDEO_CALL_ACCEPT", ENCODING):
                    target_name = self._safe_recv(client).decode(ENCODING)
                    receiver_username = target_name
                    self.send_to_one(target_name, msg, False)
                    if msg == bytes("VIDEO_CALL_ACCEPT", ENCODING):
                        is_video = True
                        client.send(bytes("READY_FOR_VIDEO_CALL", ENCODING))

                else:
                    # normal msg, broadcast to all
                    self.broadcast(username, msg.decode(ENCODING))

    def get_receiver_confirmation(self, client, source, target):
        '''
        Gets confirmation of whether target is willing to accept a video call
        '''
        print("Getting confirmation from %s for %s" %(target, source))
        msg = bytes("VIDEO_CALL_REQUEST$%s" %(source), ENCODING)
        self.send_to_one(target, msg, False)

        confirmation = self._safe_recv(client).decode(ENCODING)
        if confirmation == "VIDEO_CALL_ACCEPT":
            self._busy_clients.add(source)
            self._busy_clients.add(target)
            return True
        elif confirmation == "VIDEO_CALL_ABORT":
            return False

    def get_online_users(self, initiator_username):
        '''
        Send all online users separated by $ to initiator
        '''
        users = ""
        for u in self.clients.keys():
            if u != initiator_username and u not in self._busy_clients:
                users = users + u + "$"
        msg = bytes(users, ENCODING)
        return msg

    def broadcast(self, sender, msg):
        for u, c in self.clients.items():
            if sender:
                c[0].send(bytes("%s: %s" %(sender, msg), ENCODING))
            else:
                c[0].send(bytes("%s" %(msg), ENCODING))

    def send_to_one(self, target, msg, is_video=True):
        c = self.clients[target]
        if is_video:
            c[1].vsend(msg)
        else:
            c[0].send(msg)

if __name__ == "__main__":
    s = Server()
    s.server.listen(10)
    print("Server is ON. Waiting for clients to connect!!!")
    accept_thread = threading.Thread(target=s.accept_conn)
    accept_thread.start()
    accept_thread.join()
    s.server.shutdown(socket.SHUT_RDWR)
    s.server.close()
