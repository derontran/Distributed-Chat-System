import socket
import sys
import select
import json
import queue
from zeroconf import ServiceBrowser, Zeroconf, IPVersion, ServiceInfo
import argparse
import logging
import time


class MyListener:
    def remove_service(self, zeroconf, type, name):
        print("Service removed %s " % (name,))
        info = zeroconf.get_service_info(type, name)
        if info:
            addr, port = (socket.inet_ntoa(info.addresses[-1]), info.port)
            if addr != ip:
                serviceInfo.pop((addr, port))
                # print(serviceInfo)
                # print(addr)
                # print(port)
                # print(len(serviceInfo))

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            print("Service added: %s, service info: %s" % (name, info))
            addr, port = (socket.inet_ntoa(info.addresses[-1]), info.port)
            if addr != ip:
                serviceInfo[(addr, port)] = time.perf_counter()
                # print(serviceInfo)
                # print(addr)
                # print(port)
                # print(len(serviceInfo))

    def update_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            print("Service update %s, service info: %s" % (name, info))

    #       addr,port = (socket.inet_ntoa(info.addresses[-1]),info.port)
    #       serviceInfo[(addr,port)] =time.perf_counter()
    # print(serviceInfo)
    # print(len(serviceInfo))
    #       print(addr)
    #       print(port)
    #       serviceInfo.pop((addr,port))


def mysend(sock, msg, msglength):
    totalsent = 0
    while totalsent < msglength:
        sent = sock.send(msg[totalsent:])
        # if sent == 0:
        #     raise RuntimeError("socket connection broken")
        totalsent = totalsent + sent
    return totalsent


def myreceive(sock):
    chunks = ""
    bytes_recd = 0
    chunk = sock.recv(1024)
    if chunk == b"":
        return chunks
    if chunk == b"\xff\xf4\xff\xfd\x06":
        return "EXIT"
    chunk = chunk.decode()
    if chunk.find("\0") > 0:
        chunk.replace("\0", "")
    chunks += chunk
    bytes_recd = bytes_recd + len(chunk)

    return chunks


def sendUdp(sock, message):
    for tuple in list(serviceInfo):
        sock.sendto(bytes(json.dumps(message), "utf-8"), tuple)


def checkAddrTimeOut():

    for tuple in list(serviceInfo):
        pre = serviceInfo[tuple]
        now = time.perf_counter()
        if (now - pre) >= 120:
            serviceInfo.pop(tuple)
        else:
            serviceInfo[tuple] = now


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument("--v6", action="store_true")
    version_group.add_argument("--v6-only", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("zeroconf").setLevel(logging.DEBUG)
    if args.v6:
        ip_version = IPVersion.All
    elif args.v6_only:
        ip_version = IPVersion.V6Only
    else:
        ip_version = IPVersion.V4Only

    desc = {}
    # gethostbyname(gethostname)
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    info = ServiceInfo(
        "_p2pchat._udp.local.",
        "Tran'server at {}._p2pchat._udp.local.".format(hostname),
        addresses=[socket.inet_aton(ip)],
        port=16065,
        properties=desc,
        server="{}.local.".format(hostname),
    )

    zeroconf = Zeroconf(ip_version=ip_version)
    print("Registration of a service, press Ctrl-C to exit...")
    zeroconf.register_service(info)
    serviceInfo = {}

    listener = MyListener()
    browser = ServiceBrowser(zeroconf, "_p2pchat._udp.local.", listener)
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # non-blocking, so that select can deal with the multiplexing
    serversocket.setblocking(False)

    # bind the socket to a public host, and a well-known port
    print("listening on interface " + hostname)
    # This accepts a tuple...
    serversocket.bind((socket.gethostname(), 16065))

    # also listen on local
    localsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # non-blocking, so that select can deal with the multiplexing
    localsocket.setblocking(False)
    # This accepts a tuple...
    done = False
    try:
        localsocket.bind(("127.0.0.1", 15065))
        localsocket.listen(socket.SOMAXCONN)
    except socket.error as e:
        print ("unable to bind with '{0}'".format(e.strerror))
        localsocket.close()
        serversocket.close()
        done = True 

    inputs = [serversocket, localsocket]
    outputs = [serversocket]  # None
    server_message_queue = []
    client_message_queue = {}
    start = end = 0

    while inputs and not done:  # FOREVAR
        try:
            end = time.perf_counter()
            if (end - start) >= 60:
                outputs.append(serversocket)
            print("waiting for input")
            readable, writable, exceptional = select.select(
                inputs, outputs, inputs, 120
            )

            for source in readable:  # got something to read
                if source is localsocket:  # from local
                    print("heard locally:")
                    newClientSock, clientAddr = source.accept()
                    # data, addr = source.recvfrom(1024)
                    newClientSock.setblocking(False)
                    print(
                        "New client connected! Received from client address: {}\n".format(
                            clientAddr
                        )
                    )
                    inputs.append(newClientSock)
                    client_message_queue[newClientSock] = []
                elif source is serversocket:  # from other node
                    print("heard externally:")
                    try:
                        data, addr = source.recvfrom(1024)
                        data = data.decode()
                        print("Received from other node's address: {}\n".format(addr))
                        print(data)
                        jsondata = json.loads(data)
                        if (
                            "command"
                            or ("command" and "message" and "user") in jsondata
                        ):
                            if jsondata["command"] == "PING":
                                pre = serviceInfo[addr]
                                now = time.perf_counter()
                                if (now - pre) >= 120:
                                    serviceInfo.pop(addr)
                                else:
                                    serviceInfo[addr] = now
                                # alive
                            elif jsondata["command"] == "MSG":
                                for eachClientQueue in client_message_queue:
                                    client_message_queue[eachClientQueue].append(
                                        jsondata["message"]
                                    )
                                    for sock in inputs:
                                        if sock is not (localsocket or serversocket):
                                            outputs.append(sock)
                        else:
                            print("receive invalid input!")
                    except Exception as e:
                        print(e)
                else:  # got client message
                    checkAddrTimeOut()  # check time out for all the nodes
                    message = {"command": "MSG", "user": "Thai Tran"}
                    data = myreceive(source)
                    if data and data != "EXIT":
                        print(
                            "received {} from client: {}".format(
                                data, source.getpeername()
                            )
                        )
                        message["message"] = data
                        server_message_queue.append(message)
                        for eachClientQueue in client_message_queue:
                            if(eachClientQueue!= source):
                                client_message_queue[eachClientQueue].append(data)

                        for sock in inputs:
                            if sock is not (source or localsocket or serversocket):
                                if sock not in outputs:
                                    outputs.append(sock)
                        outputs.append(serversocket)
                    else:  # Catch client exit
                        print("probably caused by Ctrl+C")
                        print("client exit")
                        if source in outputs:
                            outputs.removes(source)
                        inputs.remove(source)
                        source.close()

            for source in writable:  # got something ready to write
                if source is serversocket:  # Server socket ready
                    if (end - start) >= 60:  # check if it is time to ping
                        sendUdp(source, {"command": "PING"})
                        start = time.perf_counter()
                    else:  # Send message to other node
                        if len(server_message_queue) != 0:
                            next_msg = server_message_queue.pop()
                            sendUdp(source, next_msg)
                else:  # Client socket ready
                    if client_message_queue[source]:
                        next_msg = client_message_queue[source].pop()
                        print("sending %s to %s" % (next_msg, source.getpeername()))
                        next_msg = bytes(next_msg, "utf-8")
                        numsend = mysend(source, next_msg, len(next_msg))
                outputs.remove(source)
            for source in exceptional:
                print("handling exceptional condition for %s" % source.getpeername())
                # Stop listening for input on the connection
                inputs.remove(source)
                if source in outputs:
                    outputs.remove(source)
                source.close()
                # Remove message queue
                del message_queue[source]
        except KeyboardInterrupt:
            print("I guess I'll just die")
            # localsocket.close()
            # serversocket.close()
            for sock in inputs:
                sock.close()
            for sock in outputs:
                sock.close()
            zeroconf.unregister_service(info)
            zeroconf.close()
            sys.exit(0)

