import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

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
    script_path = Path(os.environ["NDN_SCRIPT_PATH"])
    if not script_path.is_file():
        raise FileNotFoundError(f"NDN script not found: {script_path}")
    host, port = await wait_for_nfd()
    logging.info("Connecting to NFD: %s:%s", host, port)
    environment = os.environ.copy()
    environment["NDN_CLIENT_TRANSPORT"] = f"tcp4://{host}:{port}"
    deadline = asyncio.get_running_loop().time() + 180
    while asyncio.get_running_loop().time() < deadline:
        logging.info("Running NDN script: %s", script_path)
        process = await asyncio.create_subprocess_exec(
            "ndnc", "run", str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            if stderr:
                logging.info("ndnc stderr: %s", stderr.decode("utf-8", errors="replace").strip())
            print(stdout.decode("utf-8"), end="", flush=True)
            return
        logging.info("Function route/response not ready: %s", stderr.decode(
            "utf-8", errors="replace").strip())
        await asyncio.sleep(2)
    raise RuntimeError("ndnc run did not complete within 180 seconds")

try:
    asyncio.run(main())
except Exception as exc:
    logging.error("Function invocation failed: %s", exc)
    raise SystemExit(1)
