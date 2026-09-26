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
    prefix = os.environ["FUNCTION_PREFIX"].rstrip("/")
    args = json.loads(os.environ["FUNCTION_ARGS"])
    if not prefix.startswith("/") or not prefix or not isinstance(args, list):
        raise ValueError("FUNCTION_PREFIX must be an NDN prefix and FUNCTION_ARGS a JSON array")
    interest_name = prefix + "/(" + ",".join(str(arg) for arg in args) + ")"
    host, port = await wait_for_nfd()
    logging.info("Connecting to NFD: %s:%s", host, port)
    app = NDNApp(face=TcpFace(host, port), keychain=KeychainDigest())

    async def invoke():
        deadline = asyncio.get_running_loop().time() + 180
        try:
            while asyncio.get_running_loop().time() < deadline:
                logging.info("Calling function: %s", interest_name)
                try:
                    # Send the call directly. Do not fetch /code or execute locally.
                    name, _, content = await app.express_interest(
                        interest_name, must_be_fresh=True, can_be_prefix=False,
                        lifetime=min(30000, max(1, int((deadline - asyncio.get_running_loop().time()) * 1000))))
                    result = bytes(content or b"").decode("utf-8")
                    if result.lstrip().lower().startswith("error:"):
                        raise RuntimeError(result)
                    logging.info("Response name: %s", Name.to_str(name))
                    print("Result: " + result, flush=True)
                    return
                except (InterestNack, InterestTimeout) as exc:
                    logging.info("Function route/response not ready (%s); retrying", type(exc).__name__)
                    await asyncio.sleep(2)
            raise RuntimeError("No function response within 180 seconds")
        finally:
            app.shutdown()

    await app.main_loop(after_start=invoke())

try:
    asyncio.run(main())
except Exception as exc:
    logging.error("Function invocation failed: %s", exc)
    raise SystemExit(1)
