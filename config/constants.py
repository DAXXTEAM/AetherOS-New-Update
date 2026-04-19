"""Global constants for AetherOS v3.0   The Singularity."""
import os

# System Identity
SYSTEM_NAME = "AetherOS"
SYSTEM_VERSION = "3.0.0"
SYSTEM_CODENAME = "The Singularity"

# Agent Roles
ROLE_ARCHITECT = "architect"
ROLE_EXECUTOR = "executor"
ROLE_AUDITOR = "auditor"
ROLE_RESEARCHER = "researcher"
ROLE_GUARDIAN = "guardian"

# Model Provider Keys
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GOOGLE = "google"
PROVIDER_OLLAMA = "ollama"

# Default model mappings
DEFAULT_MODELS = {
    PROVIDER_OPENAI: "gpt-4o",
    PROVIDER_ANTHROPIC: "claude-3-5-sonnet-20241022",
    PROVIDER_GOOGLE: "gemini-1.5-pro",
    PROVIDER_OLLAMA: "llama3:latest",
}

# Security Constants
MAX_SHELL_TIMEOUT = 300
ALLOWED_SHELL_COMMANDS = [
    "ls", "cat", "head", "tail", "grep", "find", "wc", "echo",
    "mkdir", "cp", "mv", "touch", "chmod", "chown", "df", "du",
    "ps", "top", "whoami", "date", "uname", "python3", "pip",
    "git", "curl", "wget", "tar", "zip", "unzip", "sed", "awk",
]
BLOCKED_SHELL_PATTERNS = [
    "rm -rf /", "mkfs", ":(){", "dd if=/dev/zero",
    "chmod -R 777 /", "shutdown", "reboot", "halt",
    "> /dev/sda", "mv / ", r"wget .+\|.+sh", r"curl .+\|.+bash",
]

# Memory
CHROMA_COLLECTION = "aether_memory"
CHROMA_PERSIST_DIR = os.path.expanduser("~/.aetheros/chromadb")

# Logging
LOG_DIR = os.path.expanduser("~/.aetheros/logs")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Kill Switch
KILL_SWITCH_FILE = os.path.expanduser("~/.aetheros/.killswitch")
KILL_SWITCH_ENGAGED = False

# Status Codes
STATUS_IDLE = "idle"
STATUS_PLANNING = "planning"
STATUS_EXECUTING = "executing"
STATUS_AUDITING = "auditing"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"
STATUS_KILLED = "killed"

# Mesh Network
MESH_DISCOVERY_PORT = 51337
MESH_TRANSPORT_PORT = 51338
MESH_MAGIC = b"AETHER"

# Evolution Engine
EVOLUTION_BACKUP_DIR = os.path.expanduser("~/.aetheros/evolution/backups")
EVOLUTION_MAX_PATCHES = 5

# Sentinel
SENTINEL_SCAN_INTERVAL = 5.0
SENTINEL_AUTO_BLOCK = True

# Biometric
BIOMETRIC_MAX_FAILURES = 5
BIOMETRIC_LOCKOUT_MINUTES = 15

# Quantum Engine
QUANTUM_DEFAULT_QUBITS = 8
BB84_KEY_LENGTH = 256

#  
# v3.0 The Singularity   New Constants
#  

# Blockchain
BLOCKCHAIN_DIFFICULTY = 2
BLOCKCHAIN_BLOCK_INTERVAL = 30
BLOCKCHAIN_PERSIST_DIR = os.path.expanduser("~/.aetheros/blockchain")
BLOCKCHAIN_SECRET_KEY = "aetheros-v3-blockchain-integrity-key"

# Honeypot
HONEYPOT_BASE_DIR = os.path.expanduser("~/.aetheros/honeypots")
HONEYPOT_MONITOR_INTERVAL = 60.0
HONEYPOT_AUTO_DEPLOY = True

# OSINT
OSINT_SCAN_INTERVAL = 3600.0
OSINT_MONITORED_DOMAINS = ["aetheros.io", "daxxteam.io"]
OSINT_IOC_DB_PATH = os.path.expanduser("~/.aetheros/ioc_db.json")

# Nexus (Voice + Vision)
NEXUS_WAKE_WORDS = ["hey aether", "aether", "ok aether"]
NEXUS_VOICE_SAMPLE_RATE = 16000
NEXUS_VISION_FPS = 30
NEXUS_LOCKDOWN_SOFT_TIMEOUT = 30.0
NEXUS_LOCKDOWN_MEDIUM_TIMEOUT = 120.0

# Localization
DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ["en", "hi", "es"]

# Telemetry
TELEMETRY_COLLECTION_INTERVAL = 10.0
TELEMETRY_RETENTION_SECONDS = 3600
TELEMETRY_ENABLED = True

# API
API_HOST = "0.0.0.0"
API_PORT = 8080
API_AUTH_ENABLED = True

# Plugins
PLUGIN_DIR = os.path.expanduser("~/.aetheros/plugins")
PLUGIN_AUTO_LOAD = True
