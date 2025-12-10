"""
Integration tests for the firewall functionality.

These tests verify that:
- Blocked domains are actually blocked
- Whitelisted domains are accessible
- Dynamic domain approval works
"""

import pytest

from conftest import DevContainer


def describe_firewall():
    """Tests for the iptables/ipset firewall."""

    @pytest.mark.integration
    def it_blocks_non_whitelisted_domains(devcontainer: DevContainer):
        """Verify that domains not in the whitelist are blocked."""
        # example.com is not in our whitelist
        result = devcontainer.exec(
            "curl --connect-timeout 5 -s https://example.com",
            timeout=15,
        )
        # Should fail - either connection refused or timeout
        assert result.returncode != 0, (
            f"Expected blocked domain to fail, but curl succeeded: {result.stdout}"
        )

    @pytest.mark.integration
    def it_allows_whitelisted_domains(devcontainer: DevContainer):
        """Verify that whitelisted domains are accessible."""
        # api.github.com is in our whitelist
        result = devcontainer.exec(
            "curl --connect-timeout 10 -s https://api.github.com/zen",
            timeout=20,
        )
        assert result.returncode == 0, (
            f"Expected whitelisted domain to succeed: {result.stderr}"
        )
        # GitHub zen endpoint returns a random quote
        assert len(result.stdout.strip()) > 0, "Expected non-empty response from GitHub"

    @pytest.mark.integration
    def it_allows_dynamically_approved_domains(devcontainer: DevContainer):
        """Verify that domains can be added to the whitelist at runtime."""
        # First verify httpbin.org is blocked
        result = devcontainer.exec(
            "curl --connect-timeout 5 -s https://httpbin.org/get",
            timeout=15,
        )
        # Should fail initially
        initial_blocked = result.returncode != 0

        # Add httpbin.org to the whitelist
        result = devcontainer.exec(
            "sudo /usr/local/bin/add-domain-to-firewall.sh httpbin.org",
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Failed to add domain to firewall: {result.stderr}"
        )

        # Now it should work
        result = devcontainer.exec(
            "curl --connect-timeout 10 -s https://httpbin.org/get",
            timeout=20,
        )
        assert result.returncode == 0, (
            f"Domain should be accessible after approval: {result.stderr}"
        )

        # Verify we got valid JSON back
        assert '"url"' in result.stdout, "Expected JSON response from httpbin"

        # Log whether it was initially blocked (informational)
        if not initial_blocked:
            print("Note: httpbin.org was already accessible (may be in user's approved list)")

    @pytest.mark.integration
    def it_rejects_invalid_domain_format(devcontainer: DevContainer):
        """Verify that invalid domain formats are rejected."""
        # Try to add an invalid domain
        result = devcontainer.exec(
            "sudo /usr/local/bin/add-domain-to-firewall.sh 'invalid domain with spaces'",
            timeout=10,
        )
        assert result.returncode != 0, "Should reject invalid domain format"
        assert "Invalid domain format" in result.stderr or "ERROR" in result.stderr

    @pytest.mark.integration
    def it_loads_domains_from_whitelist_file(devcontainer: DevContainer):
        """Verify that the domains file is loaded correctly."""
        # Check that the domains file exists
        result = devcontainer.exec(
            "cat /usr/local/share/whitelisted-domains.txt | grep -v '^#' | grep -v '^$' | wc -l",
            timeout=10,
        )
        assert result.returncode == 0
        domain_count = int(result.stdout.strip())
        assert domain_count > 20, f"Expected at least 20 domains, got {domain_count}"

        # Verify a known domain is in the file
        result = devcontainer.exec(
            "grep 'registry.npmjs.org' /usr/local/share/whitelisted-domains.txt",
            timeout=10,
        )
        assert result.returncode == 0, "registry.npmjs.org should be in whitelist file"
