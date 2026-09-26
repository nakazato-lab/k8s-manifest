import asyncio
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from ndn.app import NDNApp
from ndn.encoding import Name
from ndn.security import KeychainDigest
from ndn.transport.stream_face import TcpFace
from ndn.types import InterestNack, InterestTimeout


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def wait_for_nfd():
    path = Path(os.environ["NFD_CONFIG_PATH"])
    deadline = asyncio.get_running_loop().time() + 90
    while asyncio.get_running_loop().time() < deadline:
        try:
            endpoint = path.read_text().strip()
            if not endpoint or endpoint == "not available yet":
                raise ValueError("NFD endpoint is not configured yet")
            uri = urlparse(endpoint if "://" in endpoint else "tcp://" + endpoint)
            if uri.scheme not in ("tcp", "tcp4", "tcp6") or not uri.hostname:
                raise ValueError("NFD endpoint must be a TCP address")
            host, port = uri.hostname, uri.port or 6363
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 3)
            writer.close()
            await writer.wait_closed()
            return host, port
        except (OSError, ValueError, asyncio.TimeoutError) as exc:
            logging.info("Waiting for NFD: %s", exc)
            await asyncio.sleep(2)
    raise RuntimeError("NFD was not ready within 90 seconds")


async def main():
    function_path = Path(os.environ["FUNCTION_PATH"])
    function_name = function_path.stem
    source = function_path.read_text(encoding="utf-8")
    host, port = await wait_for_nfd()
    logging.info("Connecting to NFD: %s:%s", host, port)
    app = NDNApp(face=TcpFace(host, port), keychain=KeychainDigest())
    params = json.dumps({
        "name": function_name,
        "content": source,
        "content_type": "ndn",
    }).encode("utf-8")
    register_name = os.getenv("MANAGER_REGISTER_NAME", "/Manager/register")

    async def register():
        try:
            logging.info("Sending register Interest: %s (name=%s, file=%s)",
                         register_name, function_name, function_path)
            _, _, content = await app.express_interest(
                Name.from_str(register_name), app_param=params,
                must_be_fresh=True, can_be_prefix=False, lifetime=6000)
            response = bytes(content or b"").decode("utf-8")
            logging.info("Manager response: %s", response)
            print(response, flush=True)
        except InterestNack as exc:
            raise RuntimeError(f"Manager NACK: {exc.reason}") from exc
        except InterestTimeout as exc:
            raise RuntimeError("Timeout waiting for Manager response") from exc
        finally:
            app.shutdown()

    await app.main_loop(after_start=register())


try:
    asyncio.run(main())
except Exception as exc:
    logging.error("Function registration failed: %s", exc)
    raise SystemExit(1)
