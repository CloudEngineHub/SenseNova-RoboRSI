# Copyright (c) 2026 DexJoCo Evaluation Contributors.
# Derived from the MIT-licensed DexJoCo evaluation release.
# See benchmarks/dexjoco/LICENSE.reference.

"""Extend only DexJoCo's terminal step comparison in memory for paired rollouts."""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
import types


def _rewritten_step(
    source: str, standard_limit: int, extended_limit: int, globals_: dict
) -> tuple[types.FunctionType, str]:
    tree = ast.parse(textwrap.dedent(source))
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Expected one DexJoCo step method")
    method = tree.body[0]
    if method.name != "step" or method.decorator_list:
        raise ValueError("Cannot safely extend decorated or unexpected step method")
    matches = []
    for node in ast.walk(method):
        if not (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.GtE)
            and len(node.comparators) == 1
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "env_step"
            and isinstance(node.left.value, ast.Name)
            and node.left.value.id == "self"
        ):
            continue
        comparator = node.comparators[0]
        if isinstance(comparator, ast.Constant) and type(comparator.value) is int:
            value = comparator.value
        elif isinstance(comparator, ast.Name) and comparator.id == "_MAX_EPISODE_STEPS":
            value = globals_.get(comparator.id)
        else:
            continue
        if value == standard_limit:
            matches.append(node)
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one {standard_limit}-step terminal comparison; got {len(matches)}"
        )
    matches[0].comparators[0] = ast.Constant(extended_limit)
    ast.fix_missing_locations(tree)
    namespace: dict = {}
    exec(compile(tree, "<dexjoco_extended_step>", "exec"), globals_, namespace)
    transformed = ast.dump(tree, include_attributes=False)
    return namespace["step"], hashlib.sha256(transformed.encode()).hexdigest()


def extend_episode_limit(env, standard_limit: int, multiplier: int) -> dict:
    """Bind a modified step method to one environment; leave upstream files clean."""
    if type(multiplier) is not int or multiplier < 2:
        raise ValueError("Extended horizon multiplier must be an integer >= 2")
    target = env
    wrapper_chain = []
    seen = set()
    while hasattr(target, "env"):
        if id(target) in seen:
            raise ValueError("Cyclic environment wrapper chain")
        seen.add(id(target))
        wrapper_chain.append(f"{type(target).__module__}.{type(target).__qualname__}")
        target = target.env
    original = type(target).step
    if original.__closure__ is not None:
        raise ValueError("Cannot safely extend a step method with closures")
    source = inspect.getsource(original)
    extended = standard_limit * multiplier
    function, ast_sha256 = _rewritten_step(
        source, standard_limit, extended, original.__globals__
    )
    target.step = types.MethodType(function, target)
    return {
        "mechanism": "in_memory_step_comparison_replacement",
        "environment_class": f"{type(target).__module__}.{type(target).__qualname__}",
        "wrapper_chain": wrapper_chain,
        "standard_step_limit": standard_limit,
        "extended_step_limit": extended,
        "original_step_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "extended_step_ast_sha256": ast_sha256,
    }
