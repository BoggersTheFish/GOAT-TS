"""
Memory state and activation decay. Usage-based state transitions (high act → active,
low over time → dormant/deep). Decay activations over simulated ticks. Hook for
periodic calls from the AGI/reasoning loop.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from src.graph.models import MemoryState, Node

logger = logging.getLogger(__name__)

# Thresholds for state transitions
ACTIVE_THRESHOLD = 0.5
DORMANT_THRESHOLD = 0.1
# Activation decay per tick (exponential)
DEFAULT_DECAY_RATE = 0.95
# After this many ticks at low activation, transition to DEEP
TICKS_TO_DEEP = 3


def decay_activations(
    nodes: list[Node],
    decay_rate: float = DEFAULT_DECAY_RATE,
    *,
    floor: float = 0.0,
) -> list[Node]:
    """Apply exponential decay to node activations: act_new = act * decay_rate, with floor."""
    out = []
    for n in nodes:
        new_act = max(floor, float(n.activation) * decay_rate)
        out.append(replace(n, activation=new_act))
    return out


def transition_states(
    nodes: list[Node],
    *,
    active_threshold: float = ACTIVE_THRESHOLD,
    dormant_threshold: float = DORMANT_THRESHOLD,
) -> list[Node]:
    """
    Usage-based state transitions: activation >= active_threshold → ACTIVE,
    activation < dormant_threshold → DORMANT (or keep DEEP if already DEEP).
    """
    out = []
    for n in nodes:
        a = n.activation
        if a >= active_threshold:
            new_state = MemoryState.ACTIVE
        elif a < dormant_threshold:
            new_state = MemoryState.DORMANT if n.state != MemoryState.DEEP else MemoryState.DEEP
        else:
            new_state = n.state
        out.append(replace(n, state=new_state))
    return out


def apply_decay_and_transitions(
    nodes: list[Node],
    decay_rate: float = DEFAULT_DECAY_RATE,
    *,
    active_threshold: float = ACTIVE_THRESHOLD,
    dormant_threshold: float = DORMANT_THRESHOLD,
) -> list[Node]:
    """Decay activations then apply state transitions. One "tick" of memory management."""
    nodes = decay_activations(nodes, decay_rate=decay_rate)
    return transition_states(nodes, active_threshold=active_threshold, dormant_threshold=dormant_threshold)


def promote_to_deep_after_ticks(
    nodes: list[Node],
    low_activation_ticks: dict[str, int],
    *,
    dormant_threshold: float = DORMANT_THRESHOLD,
    ticks_required: int = TICKS_TO_DEEP,
) -> tuple[list[Node], dict[str, int]]:
    """
    For nodes that have been below dormant_threshold for ticks_required consecutive
    ticks, set state to DEEP. low_activation_ticks maps node_id -> count of consecutive
    low-activation ticks. Returns (updated nodes, updated tick counts).
    """
    updated_ticks = dict(low_activation_ticks)
    out = []
    for n in nodes:
        if n.activation < dormant_threshold:
            count = updated_ticks.get(n.node_id, 0) + 1
            updated_ticks[n.node_id] = count
            if count >= ticks_required:
                out.append(replace(n, state=MemoryState.DEEP))
            else:
                out.append(n)
        else:
            updated_ticks[n.node_id] = 0
            out.append(n)
    return out, updated_ticks


def memory_tick(
    nodes: list[Node],
    low_activation_ticks: dict[str, int] | None = None,
    *,
    decay_rate: float = DEFAULT_DECAY_RATE,
    active_threshold: float = ACTIVE_THRESHOLD,
    dormant_threshold: float = DORMANT_THRESHOLD,
    ticks_to_deep: int = TICKS_TO_DEEP,
) -> tuple[list[Node], dict[str, int]]:
    """
    One tick of memory management for the AGI/reasoning loop. Decays activations,
    applies state transitions (ACTIVE/DORMANT), and promotes long-dormant nodes to DEEP.
    Returns (updated nodes, updated low_activation_ticks for next call).
    """
    ticks = low_activation_ticks if low_activation_ticks is not None else {}
    nodes = apply_decay_and_transitions(
        nodes,
        decay_rate=decay_rate,
        active_threshold=active_threshold,
        dormant_threshold=dormant_threshold,
    )
    nodes, ticks = promote_to_deep_after_ticks(
        nodes,
        ticks,
        dormant_threshold=dormant_threshold,
        ticks_required=ticks_to_deep,
    )
    return nodes, ticks
