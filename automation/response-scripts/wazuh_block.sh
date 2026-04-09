#!/bin/sh
# Wazuh Active Response script to block IPs using iptables

ACTION=$1
USER=$2
IP=$3

if [ -z "$IP" ]; then
    echo "No IP provided"
    exit 1
fi

case "$ACTION" in
    add)
        iptables -I INPUT -s "$IP" -j DROP
        echo "Blocked IP: $IP"
        ;;
    delete)
        iptables -D INPUT -s "$IP" -j DROP
        echo "Unblocked IP: $IP"
        ;;
    *)
        echo "Invalid action: $ACTION"
        exit 1
        ;;
esac
