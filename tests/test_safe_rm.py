"""
Integration tests for the safe-rm wrapper.

These tests verify that:
- Deletion is blocked when there are uncommitted changes
- Deletion is allowed when the git state is clean
- safe-rm works normally outside of git repos
"""

import pytest

from conftest import DevContainer


def describe_safe_rm():
    """Tests for the safe-rm deletion wrapper."""

    @pytest.mark.integration
    def it_blocks_deletion_with_uncommitted_changes(devcontainer: DevContainer):
        """Verify that safe-rm refuses to delete files when there are uncommitted changes."""
        # Create a git repo with uncommitted changes
        result = devcontainer.exec("""
            cd /tmp && rm -rf test-safe-rm && mkdir test-safe-rm && cd test-safe-rm
            git init
            git config user.email 'test@test.com'
            git config user.name 'Test'
            echo "initial" > file1.txt
            git add file1.txt
            git commit -m "initial"
            echo "uncommitted change" > file2.txt
            # Now try to delete file1.txt with uncommitted file2.txt present
            safe-rm file1.txt 2>&1
            echo "exit_code=$?"
        """, timeout=30)

        # safe-rm should fail
        assert "exit_code=1" in result.stdout, (
            f"Expected safe-rm to fail with uncommitted changes: {result.stdout}"
        )
        assert "uncommitted changes" in result.stdout.lower() or "commit" in result.stdout.lower(), (
            f"Expected error message about uncommitted changes: {result.stdout}"
        )

    @pytest.mark.integration
    def it_allows_deletion_with_clean_git_state(devcontainer: DevContainer):
        """Verify that safe-rm allows deletion when all changes are committed."""
        result = devcontainer.exec("""
            cd /tmp && rm -rf test-safe-rm-clean && mkdir test-safe-rm-clean && cd test-safe-rm-clean
            git init
            git config user.email 'test@test.com'
            git config user.name 'Test'
            echo "to be deleted" > delete-me.txt
            echo "to keep" > keep-me.txt
            git add .
            git commit -m "initial commit"
            # Git state is clean, deletion should work
            safe-rm delete-me.txt
            echo "exit_code=$?"
            # Verify file is gone
            ls delete-me.txt 2>&1 || echo "file_deleted=true"
        """, timeout=30)

        assert "exit_code=0" in result.stdout, (
            f"Expected safe-rm to succeed with clean state: {result.stdout}"
        )
        assert "file_deleted=true" in result.stdout, (
            f"File should have been deleted: {result.stdout}"
        )

    @pytest.mark.integration
    def it_works_outside_git_repos(devcontainer: DevContainer):
        """Verify that safe-rm works normally outside of git repositories."""
        result = devcontainer.exec("""
            cd /tmp && rm -rf test-non-git && mkdir test-non-git && cd test-non-git
            echo "test file" > testfile.txt
            # Not a git repo - should work without restrictions
            safe-rm testfile.txt
            echo "exit_code=$?"
            ls testfile.txt 2>&1 || echo "file_deleted=true"
        """, timeout=30)

        assert "exit_code=0" in result.stdout, (
            f"Expected safe-rm to succeed outside git repo: {result.stdout}"
        )
        assert "file_deleted=true" in result.stdout, (
            f"File should have been deleted: {result.stdout}"
        )

    @pytest.mark.integration
    def it_passes_through_rm_options(devcontainer: DevContainer):
        """Verify that safe-rm passes options through to rm."""
        result = devcontainer.exec("""
            cd /tmp && rm -rf test-rm-options && mkdir test-rm-options && cd test-rm-options
            git init
            git config user.email 'test@test.com'
            git config user.name 'Test'
            mkdir -p subdir/nested
            echo "nested file" > subdir/nested/file.txt
            git add .
            git commit -m "initial"
            # Use -rf to recursively delete
            safe-rm -rf subdir
            echo "exit_code=$?"
            ls -la subdir 2>&1 || echo "dir_deleted=true"
        """, timeout=30)

        assert "exit_code=0" in result.stdout, (
            f"Expected safe-rm -rf to succeed: {result.stdout}"
        )
        assert "dir_deleted=true" in result.stdout, (
            f"Directory should have been deleted: {result.stdout}"
        )
