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


if __name__ == "__main__":
    unittest.main()
