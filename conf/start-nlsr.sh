#!/bin/sh
set -eu
case "$POD_NAME" in
  nfd-0) peer=nfd-1; peer_service=nfd-peer-1 ;;
  nfd-1) peer=nfd-0; peer_service=nfd-peer-0 ;;
  *) echo "Unsupported router: $POD_NAME" >&2; exit 1 ;;
esac

# NLSR uses the same Pod's NFD through the shared Unix socket.
until nc -z -U /run/nfd.sock >/dev/null 2>&1; do sleep 2; done
until peer_ip=$(getent ahostsv4 "$peer_service.$POD_NAMESPACE.svc" | awk 'NR == 1 {print $1}') && [ -n "$peer_ip" ]; do
  sleep 2
done
mkdir -p /var/lib/nlsr/state
identity="/ndn/k8s/%C1.Router/$POD_NAME"
if ! ndnsec cert-dump -i "$identity" > /var/lib/nlsr/router.cert; then
  ndnsec key-gen "$identity" > /var/lib/nlsr/router.cert
  ndnsec cert-install /var/lib/nlsr/router.cert
fi
sed -e "s|@ROUTER@|$POD_NAME|g" \
    -e "s|@PEER@|$peer|g" \
    -e "s|@PEER_IP@|$peer_ip|g" \
    /config/nlsr.conf > /var/lib/nlsr/nlsr.conf
exec nlsr -f /var/lib/nlsr/nlsr.conf
