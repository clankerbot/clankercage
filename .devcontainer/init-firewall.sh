#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

# Disable IPv6 to prevent firewall bypass
# IPv6 traffic would completely bypass our iptables rules since we only configure IPv4
sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null
sysctl -w net.ipv6.conf.default.disable_ipv6=1 >/dev/null

# Parse arguments
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --verbose|-v)
            VERBOSE=true
            ;;
    esac
done

# Logging helper - only prints if verbose mode is enabled
log() {
    if $VERBOSE; then
        echo "$@"
    fi
}

# 1. Extract Docker DNS info BEFORE any flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

# Flush existing rules and delete existing ipsets
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# 2. Selectively restore ONLY internal Docker DNS resolution
if [ -n "$DOCKER_DNS_RULES" ]; then
    log "Restoring Docker DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
else
    log "No Docker DNS rules to restore"
fi

# First allow DNS and localhost before any restrictions
# Allow outbound DNS
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
# Allow inbound DNS responses
iptables -A INPUT -p udp --sport 53 -j ACCEPT
# Allow outbound SSH
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
# Allow inbound SSH responses
iptables -A INPUT -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT
# Allow localhost
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Create ipset with CIDR support
ipset create allowed-domains hash:net

# Fetch GitHub meta information and aggregate + add their IP ranges
log "Fetching GitHub IP ranges..."
gh_ranges=$(curl -s https://api.github.com/meta)
if [ -z "$gh_ranges" ]; then
    echo "WARNING: Failed to fetch GitHub IP ranges (continuing without them)"
elif ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null; then
    echo "WARNING: GitHub API response missing required fields (continuing without them)"
else
    log "Processing GitHub IPs..."
    while read -r cidr; do
        if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
            echo "WARNING: Invalid CIDR range from GitHub meta: $cidr (skipping)"
            continue
        fi
        log "Adding GitHub range $cidr"
        ipset add allowed-domains "$cidr"
    done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)
fi

# Load whitelisted domains from file
DOMAINS_FILE="/usr/local/share/whitelisted-domains.txt"
DOMAINS=()
if [ -f "$DOMAINS_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        DOMAINS+=("$line")
    done < "$DOMAINS_FILE"
    log "Loaded ${#DOMAINS[@]} domains from $DOMAINS_FILE"
else
    echo "WARNING: Domains file not found at $DOMAINS_FILE"
fi

# Resolve all domains in parallel for speed
log "Resolving domains..."
for domain in "${DOMAINS[@]}"; do
    # Run dig in background, store PID
    dig +noall +answer +time=5 +tries=2 A "$domain" > "/tmp/dns_$domain" &
done
wait  # Wait for all DNS lookups to complete

# Process results and add to ipset
for domain in "${DOMAINS[@]}"; do
    ips=$(awk '$4 == "A" {print $5}' "/tmp/dns_$domain")
    rm -f "/tmp/dns_$domain"

    if [ -z "$ips" ]; then
        echo "WARNING: Failed to resolve $domain (skipping)"
        continue
    fi

    while read -r ip; do
        if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "ERROR: Invalid IP from DNS for $domain: $ip"
            exit 1
        fi
        log "Adding $ip for $domain"
        ipset add allowed-domains "$ip" 2>/dev/null || true  # Ignore duplicates
    done < <(echo "$ips")
done

# Load user-approved domains from previous sessions
ALLOWED_FILE="/home/node/.claude/.allowed-browser-domains"
if [ -f "$ALLOWED_FILE" ]; then
    log "Loading user-approved domains..."
    while IFS= read -r domain || [ -n "$domain" ]; do
        [ -z "$domain" ] && continue
        [[ "$domain" =~ ^# ]] && continue  # Skip comments
        /usr/local/bin/add-domain-to-firewall.sh "$domain" 2>/dev/null || true
    done < "$ALLOWED_FILE"
fi

# Get host IP from default route
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi

HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
log "Host network detected as: $HOST_NETWORK"

# Set up remaining iptables rules
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# Set default policies to DROP first
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# First allow established connections for already approved traffic
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Then allow only specific outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

# Explicitly REJECT all other outbound traffic for immediate feedback
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

log "Firewall configuration complete"
log "Verifying firewall rules..."

# Run verification tests in parallel
curl --connect-timeout 3 -s https://example.com >/dev/null 2>&1 &
BLOCK_PID=$!
curl --connect-timeout 3 -s https://api.github.com/zen >/dev/null 2>&1 &
ALLOW_PID=$!

# Check blocked test (should fail)
if wait $BLOCK_PID; then
    echo "ERROR: Firewall verification failed - was able to reach https://example.com"
    exit 1
else
    log "Firewall verification passed - unable to reach https://example.com as expected"
fi

# Check allowed test (should succeed)
if ! wait $ALLOW_PID; then
    echo "WARNING: Firewall verification failed - unable to reach https://api.github.com (continuing anyway)"
else
    log "Firewall verification passed - able to reach https://api.github.com as expected"
fi
