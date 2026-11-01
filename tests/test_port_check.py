"""Start-up port check: a busy port is reported with its owner instead of a bare bind error."""

from __future__ import annotations

import socket
import unittest

from notebooklm_batch_studio.entrypoints.port_check import busy_port_message, port_is_free


class PortCheckTest(unittest.TestCase):
    """port_is_free / busy_port_message on a real socket."""

    def test_free_and_busy_port(self) -> None:
        """A port held by a listening socket is busy and the message names the port and how to look."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            port = sock.getsockname()[1]
            self.assertFalse(port_is_free("127.0.0.1", port))
            message = busy_port_message("127.0.0.1", port)
            self.assertIn(str(port), message)
            self.assertIn("PORTS.md", message)
        self.assertTrue(port_is_free("127.0.0.1", port))

    def test_recently_closed_port_is_free(self) -> None:
        """A port whose server just closed (connections in TIME_WAIT) counts as free, like uvicorn sees it."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port))
        conn, _ = server.accept()
        conn.close()  # the server side closes first, so its socket goes to TIME_WAIT
        client.close()
        server.close()
        self.assertTrue(port_is_free("127.0.0.1", port))


if __name__ == "__main__":
    unittest.main()
