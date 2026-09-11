"""Read-only TWS positions, using the same bounded protocol as the macOS client."""

from __future__ import annotations

import math
import re
import socket
import struct
import time


def _frame(*fields: str) -> bytes:
    payload = ("\0".join(fields) + "\0").encode()
    return struct.pack("!I", len(payload)) + payload


def fetch_positions(host="127.0.0.1", port=7497, client_id=17, timeout=15):
    """Return a complete snapshot or raise; partial snapshots are never applied."""
    if not host.strip() or not 1 <= port <= 65535 or not 0 <= client_id <= 2147483647:
        raise ValueError("请检查 TWS 主机、端口（1–65535）和 Client ID（非负整数）")
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=timeout) as connection:
        def read_exact(size):
            data = bytearray()
            while len(data) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("读取 TWS 持仓超时，请确认已登录并启用 Socket API")
                connection.settimeout(remaining)
                chunk = connection.recv(size - len(data))
                if not chunk:
                    raise ConnectionError("TWS 在持仓读取完成前关闭连接")
                data.extend(chunk)
            return bytes(data)

        def read_fields():
            length = struct.unpack("!I", read_exact(4))[0]
            if not 0 < length <= 16_777_216:
                raise ValueError("TWS 返回了无效的数据帧")
            return read_exact(length).decode("utf-8").rstrip("\0").split("\0")

        version = b"v100..157"
        connection.sendall(b"API\0" + struct.pack("!I", len(version)) + version)
        handshake = read_fields()
        if len(handshake) < 2 or int(handshake[0]) < 100:
            raise ValueError("TWS API 版本不兼容")
        connection.sendall(_frame("71", "2", str(client_id), ""))
        requested = False
        positions = {}
        while True:
            fields = read_fields()
            if fields[0] == "9" and not requested:
                connection.sendall(_frame("61", "1"))
                requested = True
            elif fields[0] == "61":
                version = int(fields[1])
                index = 14 if version >= 2 else 13
                if version < 3 or len(fields) <= index + 1:
                    raise ValueError("TWS 返回了不完整的持仓数据")
                quantity, cost = float(fields[index]), float(fields[index + 1])
                if not math.isfinite(quantity) or not math.isfinite(cost):
                    raise ValueError("TWS 返回了无效的数量或成本")
                positions[(fields[2], fields[3])] = {
                    "account": fields[2], "symbol": fields[4],
                    "security_type": fields[5], "currency": fields[11],
                    "quantity": quantity, "avg_cost": cost,
                }
            elif fields[0] == "62" and requested:
                connection.sendall(_frame("64", "1"))
                return list(positions.values())
            elif fields[0] == "4" and len(fields) >= 5:
                if int(fields[3]) not in {2104, 2106, 2107, 2108, 2158}:
                    raise ConnectionError(f"TWS {fields[3]}: {fields[4]}")


def merge_positions(current, snapshots, previously_imported, account=""):
    """Replace prior TWS positions, preserving unrelated manual entries."""
    scoped = [p for p in snapshots if not account or p["account"].casefold() == account.casefold()]
    if account and snapshots and not scoped:
        raise ValueError("未找到配置的 TWS 账户；原有持仓已保留，请检查账户 ID")
    totals = {}
    skipped = 0
    for position in scoped:
        quantity, cost = position["quantity"], position["avg_cost"]
        if quantity == 0:
            continue
        symbol = position["symbol"].strip().upper()
        if (position["security_type"] != "STK" or position["currency"] != "USD"
                or quantity <= 0 or cost <= 0
                or not math.isfinite(quantity) or not math.isfinite(cost)
                or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", symbol)):
            skipped += 1
            continue
        total = totals.setdefault(symbol, {"quantity": 0.0, "weighted_cost": 0.0})
        total["quantity"] += quantity
        total["weighted_cost"] += quantity * cost
    result = {symbol: value for symbol, value in current.items() if symbol not in previously_imported}
    for symbol, total in totals.items():
        result[symbol] = {"quantity": total["quantity"], "avg_cost": total["weighted_cost"] / total["quantity"]}
    return result, sorted(totals), skipped
