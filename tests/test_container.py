"""
Integration tests for the devcontainer setup.

These tests verify that:
- The container starts correctly
- Required tools are installed
- Basic functionality works
"""

import pytest

from conftest import DevContainer


def describe_container():
    """Tests for basic container functionality."""

    @pytest.mark.integration
    def it_has_claude_installed(devcontainer: DevContainer):
        """Verify that Claude Code is installed and accessible."""
        result = devcontainer.exec("claude --version", timeout=30)
        assert result.returncode == 0, f"Claude not found: {result.stderr}"
        assert "claude" in result.stdout.lower() or result.stdout.strip(), (
            f"Unexpected claude version output: {result.stdout}"
        )

    @pytest.mark.integration
    def it_has_required_tools(devcontainer: DevContainer):
        """Verify that required development tools are installed."""
        tools = ["git", "node", "npm", "pnpm", "uv", "uvx", "docker", "gh", "jq", "curl"]

        for tool in tools:
            result = devcontainer.exec(f"which {tool}", timeout=10)
            assert result.returncode == 0, f"{tool} not found in container"

    @pytest.mark.integration
    def it_runs_as_non_root_user(devcontainer: DevContainer):
        """Verify that the container runs as a non-root user."""
        result = devcontainer.exec("whoami", timeout=10)
        assert result.returncode == 0
        assert result.stdout.strip() == "node", (
            f"Expected user 'node', got '{result.stdout.strip()}'"
        )

    @pytest.mark.integration
    def it_has_firewall_initialized(devcontainer: DevContainer):
        """Verify that the firewall is set up correctly."""
        # Check that the allowed-domains ipset exists
        result = devcontainer.exec(
            "sudo ipset list allowed-domains | head -5",
            timeout=10,
        )
        assert result.returncode == 0, f"ipset not configured: {result.stderr}"
        assert "allowed-domains" in result.stdout, (
            f"allowed-domains ipset not found: {result.stdout}"
        )

    @pytest.mark.integration
    def it_has_iptables_rules(devcontainer: DevContainer):
        """Verify that iptables OUTPUT policy is DROP."""
        result = devcontainer.exec(
            "sudo iptables -L OUTPUT -n | head -3",
            timeout=10,
        )
        assert result.returncode == 0, f"iptables failed: {result.stderr}"
        # The default policy should be DROP
        assert "DROP" in result.stdout or "policy DROP" in result.stdout.lower(), (
            f"OUTPUT policy should be DROP: {result.stdout}"
        )

    @pytest.mark.integration
    def it_has_zsh_configured(devcontainer: DevContainer):
        """Verify that zsh is the default shell with oh-my-zsh."""
        result = devcontainer.exec("echo $SHELL", timeout=10)
        assert result.returncode == 0
        assert "zsh" in result.stdout, f"Expected zsh shell: {result.stdout}"

        # Check oh-my-zsh is installed
        result = devcontainer.exec("ls ~/.oh-my-zsh", timeout=10)
        assert result.returncode == 0, "oh-my-zsh not installed"

    @pytest.mark.integration
    def it_has_working_dns(devcontainer: DevContainer):
        """Verify that DNS resolution works inside the container."""
        result = devcontainer.exec("dig +short github.com A", timeout=15)
        assert result.returncode == 0, f"DNS resolution failed: {result.stderr}"
        # Should get at least one IP back
        assert result.stdout.strip(), "DNS returned no results for github.com"
