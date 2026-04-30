#!/usr/bin/env python3
"""Build a hierarchical cluster tree of Meta vacancies for radial-tree viz.

Reads:  ../public/online_scraped.json
Writes: ../public/vacancy_tree.json

Structure:
  root → teams[0] → sub_teams[0] → seniority bucket → role nodes

Hierarchy is rule-based (regex on title) — no LLM round-trip per role. The LLM
is only used for the cluster-level "what does this team do?" summary, which is
optional (skipped if no model is reachable). Results are cached on disk.

Usage:
    uv run python scripts/build_vacancy_tree.py                # no LLM
    uv run python scripts/build_vacancy_tree.py --llm ollama   # ChatOllama
    uv run python scripts/build_vacancy_tree.py --llm openai   # ChatOpenAI
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent  # tools/cv_matcher
INPUT = ROOT.parent.parent / "public" / "online_scraped.json"
OUTPUT = ROOT.parent.parent / "public" / "vacancy_tree.json"
LLM_CACHE = ROOT / ".cache" / "vacancy_tree_llm.json"


# ────────────────────────────────────────────────────────────────────────
# Seniority parser — ordered most-specific first; stop at first match.
# ────────────────────────────────────────────────────────────────────────
SENIORITY_LADDER: List[Tuple[str, int, re.Pattern]] = [
    ("VP",        9, re.compile(r"\b(?:VP|Vice President)\b", re.I)),
    ("Director",  8, re.compile(r"\b(?:Sr\.?|Senior)?\s*Director\b", re.I)),
    ("Head",      7, re.compile(r"\bHead of\b", re.I)),
    ("Principal", 6, re.compile(r"\bPrincipal\b", re.I)),
    ("Manager",   5, re.compile(r"\b(?:Sr\.?|Senior)?\s*Manager\b", re.I)),
    ("Lead",      5, re.compile(r"\bLead\b", re.I)),
    ("Staff",     4, re.compile(r"\bStaff\b", re.I)),
    ("Senior",    3, re.compile(r"\b(?:Sr\.?|Senior)\b", re.I)),
    ("Junior",    1, re.compile(r"\b(?:Jr\.?|Junior|Associate|Entry)\b", re.I)),
    ("Intern",    0, re.compile(r"\bIntern\b", re.I)),
]
DEFAULT_LEVEL = ("IC", 2)  # plain "Software Engineer" / "Product Manager"


def classify_seniority(title: str) -> Tuple[str, int]:
    for name, rank, pat in SENIORITY_LADDER:
        if pat.search(title):
            return name, rank
    return DEFAULT_LEVEL


def role_stem(title: str) -> str:
    """Stem before the comma — peers share this. 'Software Engineer, ML' → 'software engineer'."""
    base = title.split(",", 1)[0]
    # Strip seniority words from stem so peers match across levels
    for _, _, pat in SENIORITY_LADDER:
        base = pat.sub("", base)
    return re.sub(r"\s+", " ", base).strip().lower()


# ────────────────────────────────────────────────────────────────────────
# Research-role detector — flags PhD/papers-required vacancies so the viewer
# can mark them with 🔬 (vs ⚙️ for engineering). Score-based: title match is
# strongest signal, team is mid, PhD+publications in description is also strong.
# ────────────────────────────────────────────────────────────────────────
# Bare "Scientist" is too broad — "Data Scientist, Analytics" is engineering,
# not research. Require a research-marker prefix.
_RESEARCH_TITLE = re.compile(
    r"\b(Research\s+(?:Scientist|Engineer|Manager|Director|Lead)|"
    r"Postdoc(?:toral)?|Applied\s+Scientist|AI\s+Research\s+Scientist)\b",
    re.IGNORECASE,
)
_RESEARCH_TEAMS = {"AI Research", "Research", "FAIR", "Reality Labs Research"}
_PHD_RE = re.compile(r"\bPh\.?\s*D\.?\b|\bDoctorate\b", re.IGNORECASE)
_PAPER_RE = re.compile(
    r"\b(?:publish(?:ed|ing|ication)s?|peer[-\s]review(?:ed)?|first[-\s]?author|"
    r"papers?\s+(?:at|in)\s+(?:top|leading|major|premier)|"
    r"top\s+(?:tier|venues|conferences)|"
    r"(?:NeurIPS|ICML|ICLR|CVPR|ACL|EMNLP|SIGGRAPH|KDD|AAAI|UAI|COLT))\b",
    re.IGNORECASE,
)


def classify_research(title: str, team: str, description: str) -> Tuple[bool, int, str]:
    """Return (is_research, score, marker_emoji).

    Scoring (≥2 → research):
      title match    +3
      team in known  +2
      PhD + papers   +2  (both required to count — PhD alone is too noisy)
      PhD alone      +1
      papers alone   +1
    """
    score = 0
    if _RESEARCH_TITLE.search(title):
        score += 3
    if team in _RESEARCH_TEAMS:
        score += 2
    has_phd = bool(_PHD_RE.search(description))
    has_pubs = bool(_PAPER_RE.search(description))
    if has_phd and has_pubs:
        score += 2
    elif has_phd or has_pubs:
        score += 1
    is_research = score >= 2
    marker = "🔬" if is_research else "⚙️"
    return is_research, score, marker


# ────────────────────────────────────────────────────────────────────────
# Product-role detector — flags PM-track vacancies so the viewer can mark
# them with 📦 and offer a "Product only" filter. Distinct from research:
# both can be true (e.g., AI Product Manager doing applied work) — we keep
# them as independent flags rather than a single mutex category.
# ────────────────────────────────────────────────────────────────────────
_PRODUCT_TITLE = re.compile(
    r"\b(?:"
    r"(?:Group\s+|Senior\s+|Sr\.?\s+|Lead\s+|Staff\s+|Associate\s+|Principal\s+)?Product\s+Manager(?:s)?"
    r"|Product\s+Lead"
    r"|Product\s+(?:Director|Owner|Strategy(?:\s+Lead|\s+Manager)?)"
    r"|Director(?:,\s+|\s+of\s+)Product"
    r"|Head\s+of\s+Product"
    r"|VP[,\s]+Product"
    r"|Chief\s+Product\s+Officer"
    r"|APM\b"
    r"|GPM\b"
    r"|TPM\b"  # Technical Program Manager — included as a Product-adjacent track
    r")\b",
    re.IGNORECASE,
)
_PRODUCT_TEAMS = {"Product Management"}


def classify_product(title: str, team: str) -> Tuple[bool, int, str]:
    """Return (is_product, score, marker_emoji). ≥2 → product."""
    score = 0
    if _PRODUCT_TITLE.search(title):
        score += 3
    if team in _PRODUCT_TEAMS:
        score += 2
    is_product = score >= 2
    marker = "📦" if is_product else ""
    return is_product, score, marker


# ────────────────────────────────────────────────────────────────────────
# Unified role-category classifier. Priority-ordered: first match wins, so
# more specific categories (research, design) come before generic ones
# (engineering). Each entry is (category_id, emoji, label, title_regex,
# team_set). Team match alone is enough; title match alone is enough; either
# triggers the category. Engineering is the catch-all default.
# ────────────────────────────────────────────────────────────────────────
CATEGORIES: List[Tuple[str, str, str, Optional[re.Pattern], Optional[set]]] = [
    ("research", "🔬", "Research",
     _RESEARCH_TITLE,
     _RESEARCH_TEAMS),
    ("design", "🎨", "Design",
     re.compile(r"\b(?:Product\s+Designer|UX\s+(?:Designer|Researcher|Engineer)|Visual\s+Designer|Content\s+Designer|Interaction\s+Designer|Industrial\s+Designer|Brand\s+Designer|Design\s+(?:Lead|Manager|Director|Strategist)|Creative\s+Director|Art\s+Director)\b", re.I),
     {"Creative", "Design"}),
    ("data", "📊", "Data",
     re.compile(r"\b(?:Data\s+(?:Scientist|Analyst|Engineer)|Quantitative\s+(?:Researcher|Analyst)|Analytics\s+(?:Lead|Manager|Engineer)|Business\s+Analyst|BI\s+(?:Engineer|Analyst))\b", re.I),
     {"Data & Analytics"}),
    ("product", "📦", "Product",
     _PRODUCT_TITLE,
     _PRODUCT_TEAMS),
    ("legal", "⚖️", "Legal/Policy",
     re.compile(r"\b(?:Counsel|Attorney|Paralegal|Compliance|Privacy(?:\s+(?:Manager|Counsel|Engineer))?|(?:Public\s+)?Policy|Regulatory|Risk\s+Manager|Trust\s+and\s+Safety\s+(?:Counsel|Policy))\b", re.I),
     None),
    ("finance", "💰", "Finance",
     re.compile(r"\b(?:Finance(?:\s+Manager|\s+Lead)?|Financial\s+Analyst|FP&A|Controller|Treasury|Tax|Accounting|Accountant|Auditor|Investor\s+Relations)\b", re.I),
     None),
    ("people", "👥", "People",
     re.compile(r"\b(?:Recruiter|Recruiting|Sourcer|HRBP|People\s+(?:Operations|Partner|Manager)|Talent\s+(?:Acquisition|Manager|Partner)|Compensation\s+Analyst|Benefits\s+Manager|Learning\s+(?:&|and)\s+Development)\b", re.I),
     None),
    ("tpm", "📋", "Program Mgmt",
     re.compile(r"\b(?:Technical\s+Program\s+Manager|TPM|Program\s+Manager|Project\s+Manager|Programme\s+Manager|Engineering\s+Program\s+Manager)\b", re.I),
     None),
    ("gtm", "💼", "GTM",
     re.compile(r"\b(?:Sales(?:\s+(?:Manager|Director|Lead|Engineer|Operations))?|Account\s+(?:Manager|Executive|Director)|Business\s+Development|BDR|Partnerships?\s+(?:Manager|Lead|Director)|Marketing(?:\s+(?:Manager|Lead|Director))?|Customer\s+(?:Success|Solutions))\b", re.I),
     {"Sales & Marketing"}),
    ("operations", "🏗️", "Operations",
     re.compile(r"\b(?:Site\s+Manager|Operations\s+(?:Manager|Lead|Director)|Supply\s+Chain|Logistics|Data\s+Center\s+(?:Operations|Technician|Manager|Engineer)|Facilities|NPI|Manufacturing)\b", re.I),
     {"Global Operations", "Data Center"}),
    ("security", "🛡️", "Security/Trust",
     re.compile(r"\b(?:Security\s+(?:Engineer|Manager|Analyst|Architect|Researcher)|Trust\s+(?:&|and)\s+Safety|Threat\s+(?:Intelligence|Analyst)|Information\s+Security|Cyber(?:security)?|Penetration\s+Tester|InfoSec)\b", re.I),
     None),
    # Engineering is the default — no patterns; assigned when nothing else matched.
]
CATEGORY_BY_ID: Dict[str, Tuple[str, str]] = {
    cid: (emoji, label) for cid, emoji, label, _, _ in CATEGORIES
}
CATEGORY_BY_ID["engineering"] = ("⚙️", "Engineering")
CATEGORY_ORDER = [c[0] for c in CATEGORIES] + ["engineering"]


def classify_category(title: str, team: str) -> Tuple[str, str, str]:
    """Return (category_id, emoji, label). First-match wins; falls back to engineering."""
    for cid, emoji, label, title_re, team_set in CATEGORIES:
        title_hit = bool(title_re and title_re.search(title))
        team_hit = bool(team_set and team in team_set)
        if title_hit or team_hit:
            return cid, emoji, label
    return "engineering", "⚙️", "Engineering"


# ────────────────────────────────────────────────────────────────────────
# Within-sub_cluster manager hierarchy — each role's manager is the
# lowest-ranked role with strictly higher level_rank in the same sub_cluster.
# Ties broken by preferring same role-stem, then deterministically by id.
# ────────────────────────────────────────────────────────────────────────
def attach_manager_hierarchy(tree: Dict[str, Any]) -> None:
    """Mutate roles in-place: add ``manager_id`` (or None for top-of-ladder)."""
    for cluster in tree["clusters"]:
        for sub in cluster["sub_clusters"]:
            roles: List[Dict[str, Any]] = []
            for b in sub["buckets"]:
                roles.extend(b["roles"])
            for r in roles:
                higher = [h for h in roles if h["level_rank"] > r["level_rank"]]
                if not higher:
                    r["manager_id"] = None
                    continue
                # Pick the lowest level_rank that's still strictly above us;
                # within that, prefer same-stem; then deterministic by id.
                higher.sort(key=lambda h: (
                    h["level_rank"],
                    0 if h["stem"] == r["stem"] else 1,
                    h["id"],
                ))
                r["manager_id"] = higher[0]["id"]


# ────────────────────────────────────────────────────────────────────────
# Tree builder
# ────────────────────────────────────────────────────────────────────────
def _bucket_label(name: str, rank: int) -> str:
    return f"{name} ({rank})"


def build_tree(vacancies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group: team → sub_team → seniority bucket → role nodes."""
    by_team: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    stem_index: Dict[str, List[str]] = defaultdict(list)  # stem → [job ids]
    title_index: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # exact title → [(team, id)]

    for v in vacancies:
        team = (v.get("teams") or ["Other"])[0]
        sub = (v.get("sub_teams") or ["General"])[0]
        title = v.get("title") or "Untitled"
        level_name, level_rank = classify_seniority(title)
        stem = role_stem(title)
        is_research, research_score, _ = classify_research(
            title, team, v.get("description") or "",
        )
        is_product, product_score, _ = classify_product(title, team)
        category_id, category_emoji, category_label = classify_category(title, team)
        # Research is a stronger signal than the priority-ordered category if
        # it fires on PhD/papers; let it override (but keep both flags).
        if is_research and category_id != "research":
            category_id, category_emoji, category_label = "research", "🔬", "Research"
        node = {
            "id": v["id"],
            "title": title,
            "company": v.get("company") or "Unknown",
            "level": level_name,
            "level_rank": level_rank,
            "stem": stem,
            "locations": v.get("locations") or [],
            "compensation": v.get("compensation") or "",
            "link": v.get("link") or "",
            "category": category_id,
            "category_emoji": category_emoji,
            "category_label": category_label,
            "is_research": is_research,
            "research_score": research_score,
            "is_product": is_product,
            "product_score": product_score,
            "marker": category_emoji,  # backwards compat
            "manager_id": None,
            "description": v.get("description") or "",
            "first_seen": v.get("first_seen") or "",
        }
        by_team[team][sub].append(node)
        stem_index[stem].append(node["id"])
        title_index[title].append((team, node["id"]))

    clusters = []
    total_research = 0
    total_product = 0
    total_categories: Dict[str, int] = defaultdict(int)
    for team, subs in sorted(by_team.items(), key=lambda kv: -sum(len(x) for x in kv[1].values())):
        sub_clusters = []
        team_size = 0
        team_research = 0
        team_product = 0
        team_categories: Dict[str, int] = defaultdict(int)
        for sub, roles in sorted(subs.items(), key=lambda kv: -len(kv[1])):
            buckets: Dict[Tuple[str, int], List[Dict[str, Any]]] = defaultdict(list)
            for r in roles:
                buckets[(r["level"], r["level_rank"])].append(r)
            bucket_nodes = []
            for (lvl, rank), members in sorted(buckets.items(), key=lambda kv: -kv[0][1]):
                bucket_nodes.append({
                    "name": _bucket_label(lvl, rank),
                    "level": lvl,
                    "level_rank": rank,
                    "size": len(members),
                    "research_count": sum(1 for r in members if r["is_research"]),
                    "product_count": sum(1 for r in members if r["is_product"]),
                    "roles": sorted(members, key=lambda r: (-r["level_rank"], r["title"])),
                })
            sub_research = sum(1 for r in roles if r["is_research"])
            sub_product = sum(1 for r in roles if r["is_product"])
            sub_categories: Dict[str, int] = defaultdict(int)
            for r in roles:
                sub_categories[r["category"]] += 1
                team_categories[r["category"]] += 1
                total_categories[r["category"]] += 1
            sub_clusters.append({
                "name": sub,
                "size": len(roles),
                "research_count": sub_research,
                "product_count": sub_product,
                "category_counts": dict(sub_categories),
                "dominant_category": max(sub_categories.items(), key=lambda kv: kv[1])[0] if sub_categories else "engineering",
                "is_research_dominant": sub_research >= max(1, len(roles) // 2),
                "is_product_dominant": sub_product >= max(1, len(roles) // 2),
                "buckets": bucket_nodes,
            })
            team_size += len(roles)
            team_research += sub_research
            team_product += sub_product
        clusters.append({
            "name": team,
            "size": team_size,
            "research_count": team_research,
            "product_count": team_product,
            "category_counts": dict(team_categories),
            "dominant_category": max(team_categories.items(), key=lambda kv: kv[1])[0] if team_categories else "engineering",
            "is_research_dominant": team_research >= max(1, team_size // 2),
            "is_product_dominant": team_product >= max(1, team_size // 2),
            "summary": "",
            "career_path": "",
            "sub_clusters": sub_clusters,
        })
        total_research += team_research
        total_product += team_product

    # Cross-team bridges: titles appearing in >1 team verbatim.
    bridges = [
        {"title": t, "team_pairs": sorted({tm for tm, _ in entries})}
        for t, entries in title_index.items()
        if len({tm for tm, _ in entries}) > 1
    ]

    # Peer index: stems shared by ≥2 jobs.
    peers = {stem: ids for stem, ids in stem_index.items() if len(ids) > 1}

    companies = sorted(set(v.get("company") or "Unknown" for v in vacancies))
    return {
        "company": " + ".join(companies) if companies else "Unknown",
        "companies": companies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_jobs": len(vacancies),
            "teams": len(clusters),
            "sub_teams": sum(len(c["sub_clusters"]) for c in clusters),
            "with_compensation": sum(1 for v in vacancies if v.get("compensation")),
            "research_roles": total_research,
            "product_roles": total_product,
            "engineering_roles": total_categories.get("engineering", 0),
            "category_counts": dict(total_categories),
            "cross_team_bridges": len(bridges),
        },
        "categories": [
            {"id": cid, "emoji": CATEGORY_BY_ID[cid][0], "label": CATEGORY_BY_ID[cid][1]}
            for cid in CATEGORY_ORDER
        ],
        "clusters": clusters,
        "cross_team_bridges": bridges,
        "peer_groups": peers,
    }


def build_tree_full(vacancies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convenience: build_tree + attach_manager_hierarchy."""
    tree = build_tree(vacancies)
    attach_manager_hierarchy(tree)
    return tree


# ────────────────────────────────────────────────────────────────────────
# LLM enrichment (optional)
# ────────────────────────────────────────────────────────────────────────
LLM_PROMPT = """You are summarising a Meta org-chart cluster for a job-search visualisation.

Team: {team}
Sub-teams: {sub_teams}
Sample titles ({n} total):
{titles}

Return JSON ONLY (no prose) with two keys:
- "summary": ONE sentence (max 140 chars) describing what this team builds.
- "career_path": short " → "-joined progression for an IC in this team (e.g. "Engineer → Senior → Staff → Principal").

JSON:"""


def _load_cache() -> Dict[str, Any]:
    if LLM_CACHE.exists():
        try:
            return json.loads(LLM_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_llm(kind: str, model: Optional[str]):
    """Return a langchain Chat model or None if init fails (so we degrade gracefully)."""
    try:
        if kind == "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(model=model or "gemma4:31b", temperature=0)
        if kind == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model or "gpt-5.4-mini", temperature=0.1)
    except Exception as e:
        print(f"  ⚠️ LLM init ({kind}) failed: {e}")
    return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first {...} object from a possibly-noisy LLM response."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def enrich_clusters(tree: Dict[str, Any], llm) -> None:
    """Populate `summary` + `career_path` for each cluster in-place. Cached."""
    cache = _load_cache()
    for c in tree["clusters"]:
        key = f"meta::{c['name']}"
        if key in cache:
            c["summary"] = cache[key].get("summary", "")
            c["career_path"] = cache[key].get("career_path", "")
            continue

        titles = sorted({
            r["title"]
            for s in c["sub_clusters"] for b in s["buckets"] for r in b["roles"]
        })
        prompt = LLM_PROMPT.format(
            team=c["name"],
            sub_teams=", ".join(s["name"] for s in c["sub_clusters"]),
            n=c["size"],
            titles="\n".join(f"- {t}" for t in titles[:25]),
        )
        try:
            resp = llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as e:
            print(f"  ⚠️ LLM error for {c['name']}: {e}")
            continue

        parsed = _extract_json(text) or {}
        c["summary"] = (parsed.get("summary") or "").strip()
        c["career_path"] = (parsed.get("career_path") or "").strip()
        cache[key] = {"summary": c["summary"], "career_path": c["career_path"]}
        print(f"  ✓ {c['name']}: {c['summary'][:80]}")
        _save_cache(cache)  # incremental save — safe to interrupt


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--llm", choices=("none", "ollama", "openai"), default="none")
    parser.add_argument("--llm-model", default=None,
                        help="Override default model id (gemma4:31b for ollama, gpt-5.4-mini for openai)")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"❌ {in_path} not found — run scripts/scrape_online.py first.")
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    # Accept Meta + Yandex (and any future sources)
    SUPPORTED_PREFIXES = ("meta_", "yandex_", "goog_")
    selected = [v for v in data.get("vacancies", []) if any(v.get("id", "").startswith(p) for p in SUPPORTED_PREFIXES)]
    if not selected:
        print(f"❌ no vacancies with prefixes {SUPPORTED_PREFIXES} in input.")
        return 1
    by_company = defaultdict(int)
    for v in selected:
        by_company[v.get("company") or "Unknown"] += 1
    print(f"📦 Loaded {len(selected)} vacancies: {dict(by_company)}")

    tree = build_tree_full(selected)
    s = tree["stats"]
    print(
        f"🌲 Tree: {s['teams']} teams, {s['sub_teams']} sub-teams, "
        f"{s['cross_team_bridges']} cross-team bridges  |  "
        f"🔬 {s['research_roles']} research / "
        f"📦 {s['product_roles']} product / "
        f"⚙️ {s['engineering_roles']} engineering"
    )

    if args.llm != "none":
        llm = _make_llm(args.llm, args.llm_model)
        if llm is not None:
            print(f"🧠 Enriching clusters with {args.llm} ({args.llm_model or 'default'})…")
            enrich_clusters(tree, llm)
        else:
            print("  ⚠️ LLM unavailable — skipping enrichment.")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
