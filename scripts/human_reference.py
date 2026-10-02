"""Local human-reference validation and blinded annotation; no production imports."""

import argparse
import base64
import copy
from collections import defaultdict
from datetime import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import re

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/operations/benchmarks/2026-09-27-reference-tooling"
SCHEMA = json.loads((PACKAGE / "schema.json").read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


def check_schema(value, schema=SCHEMA, path="$"):
    """Validate the deliberately small JSON Schema subset used by schema.json."""
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    kind = schema["type"]
    if not isinstance(value, types[kind]) or (
        kind in ("integer", "number") and isinstance(value, bool)
    ):
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid enum")
    if kind == "object":
        if set(value) != set(schema["required"]):
            raise ValueError(f"{path}: missing/extra fields {set(value) ^ set(schema['required'])}")
        for key, child in value.items():
            check_schema(child, schema["properties"][key], f"{path}.{key}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", math.inf):
            raise ValueError(f"{path}: invalid array length")
        for index, child in enumerate(value):
            check_schema(child, schema["items"], f"{path}[{index}]")
    elif kind == "string":
        if len(value.strip()) < schema.get("minLength", 0):
            raise ValueError(f"{path}: empty string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{path}: invalid pattern")
        if schema.get("format") == "date-time":
            instant(value)
    elif kind in ("integer", "number"):
        if not math.isfinite(value) or not schema.get("minimum", -math.inf) <= value <= schema.get(
            "maximum", math.inf
        ):
            raise ValueError(f"{path}: invalid number")


def indexed(rows):
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate id")
    return result


def membership(manifest):
    """Freeze source/preview identities, assignments and pair directions before annotation."""
    return {
        key: sorted(manifest[key], key=lambda row: row["id"]) for key in ("events", "assets")
    } | {
        "pairs": sorted(
            [{k: v for k, v in p.items() if k != "annotations"} for p in manifest["pairs"]],
            key=lambda row: row["id"],
        )
    }


def validate(manifest, base=Path("."), verify_files=False):
    check_schema(manifest)
    events, assets, annotators = (indexed(manifest[k]) for k in ("events", "assets", "annotators"))
    indexed(manifest["pairs"])
    if digest(membership(manifest)) != manifest["freeze"]["membership_sha256"]:
        raise ValueError("frozen membership digest mismatch")
    frozen = instant(manifest["freeze"]["at"])
    splits, lineage_families = {}, {}
    for event in events.values():
        for key in [("family", event["scene_family"]), ("event", event["id"])] + [
            ("lineage", source) for source in event["related_sources"]
        ]:
            if key in splits and splits[key] != event["split"]:
                raise ValueError("event/scene-family/related-source crosses split")
            splits[key] = event["split"]
        for source in event["related_sources"]:
            previous = lineage_families.setdefault(source, event["scene_family"])
            if previous != event["scene_family"]:
                raise ValueError("related sources must share scene family")
    source_owners = {}
    for asset in assets.values():
        if asset["event"] not in events:
            raise ValueError("unknown asset event")
        source = asset["source"]
        # Byte-identical photos cannot manufacture independent events or splits.
        for kind in ("source", "preview"):
            owner = source_owners.setdefault((kind, asset[kind]["sha256"]), asset["event"])
            if owner != asset["event"]:
                raise ValueError(f"{kind} content reused across events")
        if verify_files:
            for key in ("source", "preview"):
                path = base / asset[key]["path"]
                if file_hash(path) != asset[key]["sha256"]:
                    raise ValueError(f"{asset['id']}: {key} hash mismatch")
            with Image.open(base / asset["preview"]["path"]) as im:
                if (
                    im.format not in ("PNG", "JPEG")
                    or im.mode != "RGB"
                    or im.info.get("icc_profile")
                ):
                    raise ValueError(
                        "preview must be RGB PNG/JPEG, converted to sRGB with no embedded ICC"
                    )
                if im.size != (asset["preview"]["width"], asset["preview"]["height"]):
                    raise ValueError("preview dimension mismatch")
                if im.getexif().get(274, 1) != 1:
                    raise ValueError("preview must have orientation applied")
                im.load()
    counts = {
        split: {label: {"directions": 0, "families": set()} for label in ("cover", "negative")}
        for split in ("development", "holdout")
    }
    phenomena = {split: defaultdict(set) for split in counts}
    eligible_pairs, eligible_families, unresolved, pair_keys = [], set(), [], set()
    content_pairs = {"source": set(), "preview": set()}
    for pair in manifest["pairs"]:
        if pair["A"] not in assets or pair["B"] not in assets or pair["A"] == pair["B"]:
            raise ValueError("invalid pair assets")
        pair_key = frozenset((pair["A"], pair["B"]))
        if pair_key in pair_keys:
            raise ValueError("duplicate/reversed pair")
        pair_keys.add(pair_key)
        a, b = assets[pair["A"]], assets[pair["B"]]
        for kind, known in content_pairs.items():
            content_pair = tuple(sorted((a[kind]["sha256"], b[kind]["sha256"])))
            if content_pair in known:
                raise ValueError(f"duplicate {kind} content pair")
            known.add(content_pair)
        if a["event"] != b["event"]:
            raise ValueError("pair crosses event")
        event = events[a["event"]]
        rows = indexed(pair["annotations"])
        human = []
        for row in rows.values():
            if row["annotator"] not in annotators:
                raise ValueError("unknown annotator")
            start, end = instant(row["started_at"]), instant(row["completed_at"])
            if end <= start:
                raise ValueError("annotation completion must follow start")
            if row["origin"] == "new_human" and start < frozen:
                raise ValueError("new human annotation predates freeze")
            if row["preview_hashes"] != {"A": a["preview"]["sha256"], "B": b["preview"]["sha256"]}:
                raise ValueError("annotation preview identity mismatch")
            if row["role"] == "independent" and row["supersedes"]:
                raise ValueError("independent record cannot supersede")
            if row["role"] == "adjudication":
                if not row["supersedes"] or len(set(row["supersedes"])) != len(row["supersedes"]):
                    raise ValueError("adjudication requires distinct raw references")
                for ref in row["supersedes"]:
                    if (
                        ref not in rows
                        or rows[ref]["role"] != "independent"
                        or instant(rows[ref]["completed_at"]) >= start
                    ):
                        raise ValueError("invalid adjudication reference/time")
            for region in row["regions"]:
                x1, y1, x2, y2 = region["box"]
                if x1 >= x2 or y1 >= y2:
                    raise ValueError("region must have positive area")
            definite = {row["a_to_b"], row["b_to_a"]} & {"cover", "negative"}
            if definite and row["correspondence"] not in ("yes", "no"):
                raise ValueError("definite relation requires judgeable correspondence")
            if definite and not row["regions"] and not row["no_visible_change"]:
                raise ValueError(
                    "definite relation requires localized evidence or no-visible-change"
                )
            if row["no_visible_change"] and (row["regions"] or "negative" in definite):
                raise ValueError("no-visible-change conflicts with regions/negative")
            for direction, side in [("a_to_b", "B"), ("b_to_a", "A")]:
                if row[direction] == "negative" and not any(
                    r["side"] == side and r["importance"] == "important" for r in row["regions"]
                ):
                    raise ValueError("negative requires important target region")
            if row["origin"] == "new_human" and annotators[row["annotator"]]["kind"] == "human":
                human.append(row)
        if (
            any(
                e["origin"] != "new_still"
                for e in events.values()
                if e["scene_family"] == event["scene_family"]
            )
            or not human
        ):
            continue
        independent = [r for r in human if r["role"] == "independent"]
        # Multiple revisions by one person do not become independent consensus.
        if len({r["annotator"] for r in independent}) != len(independent):
            unresolved.append(pair["id"])
            continue
        adjudications = [r for r in human if r["role"] == "adjudication"]
        if adjudications:
            if len(adjudications) != 1 or set(adjudications[0]["supersedes"]) != {
                r["id"] for r in independent
            }:
                unresolved.append(pair["id"])
                continue
            selected = adjudications[0]
        elif independent:
            keys = ("correspondence", "a_to_b", "b_to_a", "quality", "regions", "no_visible_change")
            if len({digest({k: r[k] for k in keys}) for r in independent}) != 1:
                unresolved.append(pair["id"])
                continue
            selected = independent[0]
        else:
            continue
        if any(
            r["visibility"] != "clear" or r["importance"] in ("unknown", "preference_dependent")
            for r in selected["regions"]
        ):
            unresolved.append(pair["id"])
            continue
        # Abstention-only pairs remain in the raw manifest, but cannot supply
        # either the minimum labeled-pair count or independent-family count.
        if not {selected["a_to_b"], selected["b_to_a"]} & {"cover", "negative"}:
            continue
        eligible_pairs.append(pair["id"])
        eligible_families.add(event["scene_family"])
        split, family = event["split"], event["scene_family"]
        for key in ("a_to_b", "b_to_a"):
            label = selected[key]
            if label in counts[split]:
                counts[split][label]["directions"] += 1
                counts[split][label]["families"].add(family)
        # Unknown-only pairs do not manufacture visible category evidence.
        if {selected["a_to_b"], selected["b_to_a"]} & {"cover", "negative"}:
            for region in selected["regions"]:
                if region["importance"] in ("important", "nuisance"):
                    phenomena[split][f"{region['importance']}:{region['phenomenon']}"].add(family)
    missing = []
    if not verify_files:
        missing.append("source/preview bytes not verified")
    if not 24 <= len(eligible_pairs) <= 40:
        missing.append(f"need 24..40 new human pairs; have {len(eligible_pairs)}")
    if not 12 <= len(eligible_families) <= 20:
        missing.append(f"need 12..20 independent scene families; have {len(eligible_families)}")
    for split in counts:
        for label, item in counts[split].items():
            if item["directions"] < 6 or len(item["families"]) < 3:
                missing.append(f"{split}: {label} needs >=6 directions across >=3 families")
            item["families"] = sorted(item["families"])
        if not phenomena[split]["nuisance:illumination"]:
            missing.append(f"{split}: missing visible illumination nuisance")
        if not (
            phenomena[split]["important:hand_progression"]
            | phenomena[split]["important:expression_pose"]
        ):
            missing.append(f"{split}: missing visible hand/expression change")
    for keys in [
        ("nuisance:illumination",),
        ("important:hand_progression", "important:expression_pose"),
    ]:
        families = set().union(*(phenomena[s][k] for s in counts for k in keys))
        if len(families) < 2:
            missing.append(f"{'/'.join(keys)}: needs >=2 independent families")
    nuisance_types = {
        k
        for s in counts
        for k, families in phenomena[s].items()
        if k.startswith("nuisance:") and families
    }
    if len(nuisance_types) < 2:
        missing.append("need >=2 visible nuisance types")
    if unresolved:
        missing.append("unresolved human disagreement/revisions")
    return {
        "schema_valid": True,
        "files_verified": verify_files,
        "g1": "reference_insufficient" if missing else "quota_ready_pending_human_audit",
        "human_authenticity": "not_machine_verifiable",
        "missing": missing,
        "eligible_pairs": len(eligible_pairs),
        "independent_families": len(eligible_families),
        "directions": counts,
        "unresolved_pairs": unresolved,
        "phenomena": {s: {k: sorted(v) for k, v in phenomena[s].items() if v} for s in counts},
    }


def local_output(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT / ".local"):
        raise ValueError("outputs must be under repository .local/ (private, ignored)")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def dataset_identity(manifest):
    return digest(
        {
            "schema": manifest["schema"],
            "freeze": manifest["freeze"],
            "membership": membership(manifest),
            "annotators": sorted(manifest["annotators"], key=lambda row: row["id"]),
        }
    )


def bundle_mapping(manifest, split, annotator):
    events, assets = indexed(manifest["events"]), indexed(manifest["assets"])
    selected = [
        p
        for p in sorted(manifest["pairs"], key=lambda p: p["id"])
        if events[assets[p["A"]]["event"]]["split"] == split
    ]
    identity = dataset_identity(manifest)
    return {
        "bundle": digest({"dataset": identity, "split": split, "annotator": annotator}),
        "dataset_sha256": identity,
        "annotator": annotator,
        "split": split,
        "mapping": {f"P{i + 1:03}": p["id"] for i, p in enumerate(selected)},
    }


def render(manifest, base, split, annotator, output):
    validate(manifest, base, verify_files=True)
    people = indexed(manifest["annotators"])
    if annotator not in people or people[annotator]["kind"] != "human":
        raise ValueError("viewer requires registered human annotator")
    events, assets = indexed(manifest["events"]), indexed(manifest["assets"])
    metadata = bundle_mapping(manifest, split, annotator)
    neutral_ids = {value: key for key, value in metadata["mapping"].items()}
    panels = []
    for pair in sorted(manifest["pairs"], key=lambda p: p["id"]):
        if events[assets[pair["A"]]["event"]]["split"] != split:
            continue
        if any(row["annotator"] == annotator for row in pair["annotations"]):
            continue
        neutral = neutral_ids[pair["id"]]
        panel = {"id": neutral, "images": {}, "hashes": {}}
        for side in ("A", "B"):
            asset = assets[pair[side]]
            with Image.open(base / asset["preview"]["path"]) as source:
                im = source.convert("RGB")
                im.info.clear()
                stream = io.BytesIO()
                im.save(stream, format="PNG")
            panel["images"][side] = (
                "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()
            )
            panel["hashes"][side] = asset["preview"]["sha256"]
        panels.append(panel)
    if not panels:
        raise ValueError("no unannotated pairs for this annotator in selected split")
    payload = {
        "bundle": metadata["bundle"],
        "annotator": annotator,
        "panels": panels,
    }
    html = Path(__file__).with_name("human_reference_viewer.html").read_text()
    html = html.replace("/*PAYLOAD*/", json.dumps(payload).replace("<", "\\u003c"))
    output = local_output(output)
    if output.exists() or output.with_suffix(".mapping.json").exists():
        raise ValueError("refusing to overwrite existing viewer bundle")
    output.write_text(html)
    output.with_suffix(".mapping.json").write_text(json.dumps(metadata, indent=2) + "\n")


def merge(manifest, mapping, exported):
    manifest = copy.deepcopy(manifest)
    validate(manifest)
    if mapping != bundle_mapping(manifest, mapping["split"], mapping["annotator"]):
        raise ValueError("mapping dataset identity mismatch")
    if set(exported) != {"bundle", "annotations"} or exported["bundle"] != mapping["bundle"]:
        raise ValueError("export bundle mismatch")
    pairs = indexed(manifest["pairs"])
    seen = set()
    for entry in exported["annotations"]:
        if (
            set(entry) != {"pair", "record"}
            or entry["pair"] not in mapping["mapping"]
            or entry["pair"] in seen
        ):
            raise ValueError("invalid/duplicate exported pair")
        seen.add(entry["pair"])
        row = entry["record"]
        if row.get("annotator") != mapping["annotator"]:
            raise ValueError("export annotator mismatch")
        pairs[mapping["mapping"][entry["pair"]]]["annotations"].append(row)
    validate(manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "freeze", "viewer", "merge"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--split", choices=["development", "holdout"])
    parser.add_argument("--annotator")
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        base = args.manifest.resolve().parent
        if args.command == "validate":
            print(json.dumps(validate(manifest, base, verify_files=True), indent=2))
        elif args.command == "freeze":
            if any(p["annotations"] for p in manifest["pairs"]):
                raise ValueError("cannot refreeze annotated manifest")
            manifest["freeze"]["membership_sha256"] = digest(membership(manifest))
            validate(manifest, base, verify_files=True)
            if args.out is None or args.out.resolve().parent != base:
                raise ValueError("freeze output must share manifest directory to preserve paths")
            with local_output(args.out).open("x") as stream:
                stream.write(json.dumps(manifest, indent=2) + "\n")
        elif args.command == "viewer":
            if not args.out or not args.split or not args.annotator:
                raise ValueError("viewer requires --out --split --annotator")
            render(manifest, base, args.split, args.annotator, args.out)
        else:
            if (
                not args.mapping
                or not args.annotations
                or not args.out
                or args.out.resolve().parent != base
            ):
                raise ValueError("merge requires --mapping --annotations and --out beside manifest")
            result = merge(
                manifest,
                json.loads(args.mapping.read_text()),
                json.loads(args.annotations.read_text()),
            )
            validate(result, base, verify_files=True)
            with local_output(args.out).open("x") as stream:
                stream.write(json.dumps(result, indent=2) + "\n")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
