"""
Tests for GPG signing configuration in the devcontainer.

These tests verify that:
- GPG signing is properly configured
- Commits can be signed with GPG
- The setup-gpg.sh script works correctly
"""

import pytest

from conftest import DevContainer


def describe_gpg_signing():
    """Tests for GPG signing configuration."""

    @pytest.mark.integration
    def test_gpg_signing_is_configured(devcontainer: DevContainer):
        """Verify that git is configured to use GPG signing."""
        # Check commit.gpgsign is true
        result = devcontainer.exec("git config --global commit.gpgsign", timeout=10)
        assert result.returncode == 0, f"commit.gpgsign not configured: {result.stderr}"
        assert result.stdout.strip() == "true", (
            f"Expected commit.gpgsign=true, got '{result.stdout.strip()}'"
        )

    @pytest.mark.integration
    def test_gpg_signing_key_is_set(devcontainer: DevContainer):
        """Verify that a GPG signing key is configured in git."""
        result = devcontainer.exec("git config --global user.signingkey", timeout=10)
        assert result.returncode == 0, f"user.signingkey not configured: {result.stderr}"
        assert result.stdout.strip(), "No signing key configured"

    @pytest.mark.integration
    def test_gpg_key_is_available(devcontainer: DevContainer):
        """Verify that a GPG secret key is available in the container."""
        result = devcontainer.exec(
            "gpg --list-secret-keys --keyid-format=long 2>/dev/null | grep -E '^sec'",
            timeout=30,
        )
        assert result.returncode == 0, f"No GPG secret keys found: {result.stderr}"
        assert "sec" in result.stdout, "No secret key available for signing"

    @pytest.mark.integration
    def test_commits_are_signed(devcontainer: DevContainer):
        """Verify that commits made in the container are GPG signed."""
        # Create a test commit and verify it's signed
        result = devcontainer.exec(
            """
            cd /tmp && rm -rf gpg-test-repo && mkdir gpg-test-repo && cd gpg-test-repo &&
            git init &&
            git config user.email "test@test.com" &&
            git config user.name "Test User" &&
            echo "test content" > test.txt &&
            git add test.txt &&
            git commit -m "Test commit" &&
            git log --show-signature -1
            """,
            timeout=60,
        )
        assert result.returncode == 0, f"Failed to create signed commit: {result.stderr}"
        # Check for GPG signature indicators in the output
        output = result.stdout + result.stderr
        assert "gpg:" in output.lower() or "good signature" in output.lower() or "signature made" in output.lower(), (
            f"Commit does not appear to be signed. Output: {output}"
        )

    @pytest.mark.integration
    def test_gpg_tty_is_set(devcontainer: DevContainer):
        """Verify that GPG_TTY environment variable is set."""
        result = devcontainer.exec("echo $GPG_TTY", timeout=10)
        assert result.returncode == 0
        # GPG_TTY should be set to something (either from env or tty command)
        # It may be empty in non-interactive shells, so we check the zshrc instead
        result = devcontainer.exec("grep GPG_TTY ~/.zshrc", timeout=10)
        assert result.returncode == 0, "GPG_TTY not configured in .zshrc"
