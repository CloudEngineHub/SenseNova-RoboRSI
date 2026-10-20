# Copyright 2026 The Bench2Dex Evaluation Contributors.
# Licensed under the Apache License, Version 2.0.

"""Wire-compatible RPC with exact reads and bounded numpy decoding."""

import base64
import json

import numpy as np


def receive_exact(sock, count):
    chunks = bytearray()
    while len(chunks) < count:
        part = sock.recv(count - len(chunks))
        if not part:
            if not chunks:
                return None
            raise ConnectionError("Truncated RPC message")
        chunks.extend(part)
    return bytes(chunks)


def recv_message(sock):
    header = receive_exact(sock, 4)
    if header is None:
        return None
    size = int.from_bytes(header, "big")
    if not 0 < size <= 64 * 1024 * 1024:
        raise ValueError("Invalid RPC message size")
    raw = receive_exact(sock, size)
    if raw is None:
        raise ConnectionError("Missing RPC payload")

    def decode(obj):
        if obj.get("__numpy_array__"):
            dtype = np.dtype(obj["dtype"])
            if dtype.kind not in "biuf":
                raise ValueError("Unsupported array dtype")
            return np.frombuffer(
                base64.b64decode(obj["data"], validate=True), dtype=dtype
            ).reshape(obj["shape"])
        return obj

    return json.loads(raw, object_hook=decode)


def send_message(sock, value):
    def encode(obj):
        if isinstance(obj, np.ndarray):
            return {
                "__numpy_array__": True,
                "dtype": str(obj.dtype),
                "shape": list(obj.shape),
                "data": base64.b64encode(obj.tobytes()).decode(),
            }
        raise TypeError(type(obj).__name__)

    payload = json.dumps(value, default=encode, allow_nan=False).encode()
    sock.sendall(len(payload).to_bytes(4, "big") + payload)
