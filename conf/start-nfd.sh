#!/bin/sh
set -eu

case "$POD_NAME" in
  ndn-router-0) peer_service=nfd-peer-1 ;;
  ndn-router-1) peer_service=nfd-peer-0 ;;
  *) echo "Unsupported router: $POD_NAME" >&2; exit 1 ;;
esac

# Run in parallel so both NFDs can become ready before either connects to its peer.
(
  until timeout 5 nfdc status >/dev/null 2>&1; do sleep 2; done
  while true; do
    peer_ip=$(getent ahostsv4 "$peer_service.$POD_NAMESPACE.svc" | awk 'NR == 1 {print $1}')
    if [ -n "$peer_ip" ]; then
      peer_uri="tcp4://$peer_ip:6363"
      echo "Creating permanent NFD face to $peer_uri"
      if timeout 15 nfdc face create remote "$peer_uri" persistency permanent; then
        echo "Permanent NFD face ready: $peer_uri"
        break
      fi
    fi
    echo "Waiting for peer NFD: $peer_service"
    sleep 5
  done
) &

# Keep NFD as PID 1 so it receives container shutdown signals directly.
exec nfd --config /etc/ndn/nfd.conf
