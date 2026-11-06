"""Resolve explicit claim-specific reporting relationships, never independence."""
from .io import StudyError


def resolve_origins(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise StudyError("Expected a nonempty evidence-node list")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not {"id", "claim", "relation"} <= node.keys():
            raise StudyError("Each node requires id, claim and relation")
        if any(not isinstance(node[k], str) or not node[k].strip() for k in ("id", "claim", "relation")):
            raise StudyError("Node identifiers and relationships must be nonempty strings")
        if "parents" in node and (not isinstance(node["parents"], list) or not all(isinstance(p, str) for p in node["parents"])):
            raise StudyError("Parents must be a list of identifiers")
        if node["id"] in by_id:
            raise StudyError("Duplicate evidence node")
        if node["relation"] not in {"direct", "derived", "unknown"}:
            raise StudyError("Unknown reporting relationship")
        if node["relation"] == "derived" and not node.get("parents"):
            raise StudyError("Derived evidence must identify an upstream node")
        if node["relation"] != "derived" and node.get("parents"):
            raise StudyError("Only derived evidence can have upstream nodes")
        by_id[node["id"]] = node
    cache = {}

    def visit(node_id, active):
        if node_id in active:
            raise StudyError("Provenance cycle")
        if node_id not in by_id:
            raise StudyError("Missing upstream evidence")
        if node_id in cache:
            return cache[node_id]
        node = by_id[node_id]
        roots, unknowns = set(), set()
        if node["relation"] == "direct":
            roots.add(node_id)
        elif node["relation"] == "unknown":
            unknowns.add(node_id)
        else:
            for parent_id in node["parents"]:
                parent = by_id.get(parent_id)
                if parent is None or parent["claim"] != node["claim"]:
                    raise StudyError("Upstream links must refer to the same claim")
                r, u = visit(parent_id, active | {node_id})
                roots.update(r)
                unknowns.update(u)
        cache[node_id] = (roots, unknowns)
        return roots, unknowns

    claims = {}
    for node in nodes:
        roots, unknowns = visit(node["id"], set())
        group = claims.setdefault(node["claim"], {"reporting_origins": set(), "unresolved_nodes": set()})
        group["reporting_origins"].update(roots)
        group["unresolved_nodes"].update(unknowns)
    return {claim: {"reporting_origins": sorted(group["reporting_origins"]),
                    "unresolved_nodes": sorted(group["unresolved_nodes"]),
                    "statistical_independence": "not_established"}
            for claim, group in sorted(claims.items())}
