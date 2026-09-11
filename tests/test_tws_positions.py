import socket
import struct
import threading
import unittest

from tws_positions import _frame, fetch_positions, merge_positions


def position(symbol="AAPL", quantity=0.5, cost=100, account="test"):
    return dict(symbol=symbol, quantity=quantity, avg_cost=cost, account=account,
                security_type="STK", currency="USD")


class PositionTests(unittest.TestCase):
    def test_merge_replaces_closed_positions_and_preserves_manual(self):
        existing = {"OLD": {"quantity": 10, "avg_cost": 1}, "MANUAL": {"quantity": 2, "avg_cost": 3}}
        result, imported, skipped = merge_positions(existing, [position(), position(quantity=1.5, cost=200, account="second"), position("OLD", 0, 0)], ["OLD"])
        self.assertEqual(result["AAPL"], {"quantity": 2, "avg_cost": 175})
        self.assertNotIn("OLD", result)
        self.assertIn("MANUAL", result)
        self.assertEqual(imported, ["AAPL"])
        self.assertEqual(skipped, 0)

    def test_wrong_account_does_not_clear_positions(self):
        with self.assertRaises(ValueError):
            merge_positions({}, [position()], [], "unknown")

    def test_empty_snapshot_clears_imported(self):
        result, imported, _ = merge_positions({"AAPL": {}}, [], ["AAPL"])
        self.assertEqual((result, imported), ({}, []))

    def test_protocol_fragmentation_and_read_only_requests(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        errors = []

        def server():
            try:
                with listener, listener.accept()[0] as conn:
                    conn.settimeout(3)

                    def read(size):
                        data = b""
                        while len(data) < size:
                            part = conn.recv(size - len(data))
                            if not part:
                                raise EOFError
                            data += part
                        return data

                    def frame():
                        return read(struct.unpack("!I", read(4))[0])

                    self.assertEqual(read(4), b"API\0")
                    self.assertEqual(frame(), b"v100..157")
                    conn.sendall(_frame("157", "test"))
                    self.assertEqual(frame(), b"71\x002\x0017\0\0")
                    conn.sendall(_frame("9", "1", "1"))
                    self.assertEqual(frame(), b"61\x001\0")
                    payload = _frame("61", "3", "test", "123", "AAPL", "STK", "", "0", "", "", "SMART", "USD", "AAPL", "NMS", "0.5", "100") + _frame("62", "1")
                    for offset in range(0, len(payload), 3):
                        conn.sendall(payload[offset:offset + 3])
                    self.assertEqual(frame(), b"64\x001\0")
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        result = fetch_positions(port=listener.getsockname()[1], timeout=4)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, [position()])


if __name__ == "__main__":
    unittest.main()
