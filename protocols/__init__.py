"""AetherOS Communication Protocols — Secure inter-component messaging."""
from protocols.wire import WireProtocol, SecureChannel, MessageFrame
from protocols.consensus import RaftConsensus, ConsensusState

__all__ = ["WireProtocol", "SecureChannel", "MessageFrame", "RaftConsensus", "ConsensusState"]
