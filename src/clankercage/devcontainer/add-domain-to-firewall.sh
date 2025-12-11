#!/bin/bash
set -euo pipefail

# Adds a domain to the allowed-domains ipset
# Usage: add-domain-to-firewall.sh <domain>

if [ $# -ne 1 ]; then
    echo "Usage: $0 <domain>" >&2
    exit 1
fi

DOMAIN="$1"

# Validate domain format (basic check)
if [[ ! "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
    echo "ERROR: Invalid domain format: $DOMAIN" >&2
    exit 1
fi

# Resolve domain to IPs
IPS=$(dig +noall +answer A "$DOMAIN" | awk '$4 == "A" {print $5}')
if [ -z "$IPS" ]; then
    echo "ERROR: Failed to resolve $DOMAIN" >&2
    exit 1
fi

# Add each IP to the ipset
while read -r ip; do
    if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo "ERROR: Invalid IP from DNS for $DOMAIN: $ip" >&2
        exit 1
    fi
    # Add to ipset (ignore if already exists)
    if ipset add allowed-domains "$ip" 2>/dev/null; then
        echo "Added $ip for $DOMAIN"
    else
        echo "Already allowed: $ip for $DOMAIN"
    fi
done <<< "$IPS"

echo "Domain $DOMAIN is now allowed"
