from .backend import ProvisionerSandboxBackend
from .paths import (
    VIRTUAL_PATH_PREFIX,
    ensure_thread_dirs,
    resolve_virtual_path,
    sandbox_outputs_dir,
    sandbox_uploads_dir,
    sandbox_user_data_dir,
    sandbox_workspace_dir,
    virtual_path_for_thread_file,
)
from .provider import (
    SandboxConnection,
    ProvisionerSandboxProvider,
    get_sandbox_provider,
    init_sandbox_provider,
    sandbox_id_for_thread,
    shutdown_sandbox_provider,
)

# Compatibility aliases for legacy imports.
SandboxBackend = ProvisionerSandboxBackend
YuxiSandboxBackend = ProvisionerSandboxBackend
LocalContainerBackend = ProvisionerSandboxBackend
RemoteSandboxBackend = ProvisionerSandboxBackend
YuxiSandboxProvider = ProvisionerSandboxProvider
SandboxInfo = SandboxConnection

# Sandbox-visible paths for viewer/filesystem services.
USER_DATA_PATH = VIRTUAL_PATH_PREFIX
SKILLS_PATH = "/home/gem/skills"

# Relative host-side directory names under thread user-data.
WORKSPACE_DIR = "workspace"
UPLOADS_DIR = "uploads"
OUTPUTS_DIR = "outputs"

# Backward-compatible constants kept for old call sites.
THREADS_DIR = "threads"
LARGE_TOOL_RESULTS_DIR = "large-tool-results"
IDLE_CHECK_INTERVAL = 30

__all__ = [
    "IDLE_CHECK_INTERVAL",
    "LARGE_TOOL_RESULTS_DIR",
    "LocalContainerBackend",
    "OUTPUTS_DIR",
    "RemoteSandboxBackend",
    "SKILLS_PATH",
    "SandboxBackend",
    "SandboxInfo",
    "THREADS_DIR",
    "UPLOADS_DIR",
    "USER_DATA_PATH",
    "WORKSPACE_DIR",
    "YuxiSandboxBackend",
    "YuxiSandboxProvider",
    "ProvisionerSandboxBackend",
    "ProvisionerSandboxProvider",
    "VIRTUAL_PATH_PREFIX",
    "ensure_thread_dirs",
    "get_sandbox_provider",
    "init_sandbox_provider",
    "resolve_virtual_path",
    "sandbox_id_for_thread",
    "sandbox_outputs_dir",
    "sandbox_uploads_dir",
    "sandbox_user_data_dir",
    "sandbox_workspace_dir",
    "shutdown_sandbox_provider",
    "virtual_path_for_thread_file",
]
