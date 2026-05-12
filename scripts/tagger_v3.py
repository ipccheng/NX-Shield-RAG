#!/usr/bin/env python3
"""
tagger_v3.py — V3 Metadata Extraction for Nutanix RAG.

Combines Gemini-recommended schema (access_level, doc_type, primary_product,
mentioned_products, ecosystem_entities as native PyArrow lists) with
practical concerns: frequency-based primary_topic fallback for non-portal
content, complete folder mappings, and carried-over versions/content_types.

Usage:
    from tagger_v3 import apply_v3_tags
    tags = apply_v3_tags("AOS 6.8 includes Prism Central", "portal/prism/guide.md")
"""

import re
from typing import Dict, List, Tuple

# ─────────────────────────────────────────────────────────────────────
# ENTITY DICTIONARIES — Ecosystem (competitors + partners, separate)
# ─────────────────────────────────────────────────────────────────────
ECOSYSTEM_ENTITIES: Dict[str, str] = {
    "VMware": r"\bVMware\b|ESXi|vSAN|vSphere|VCF\b|VVF\b|Aria|vRealize|NSX[\s-]?[TX]|Horizon|vCenter",
    "Broadcom": r"\bBroadcom\b",
    "Red_Hat": r"Red[\s_]?Hat|OpenShift|Ansible|OpenStack|Ceph\b",
    "Dell": r"\bDell\b|VxRAIL|VxRail|PowerFlex|PowerScale|ECS\b|EMC\b",
    "HPE": r"\bHPE\b|SimpliVity|Alletra|Nimble\b|ProLiant|Moonshot",
    "Pure_Storage": r"Pure[\s_]?Storage|FlashArray|FlashBlade",
    "Microsoft": r"\bMicrosoft\b|Hyper[\s-]?V|Azure\b|AVS\b",
    "AWS": r"\bAWS\b|Outposts|Amazon Web Services",
    "Google_Cloud": r"Google Cloud|GCP\b",
    "Rancher": r"\bRancher\b",
    "Portworx": r"\bPortworx\b",
    "KubeVirt": r"\bKubeVirt\b",
    "Proxmox": r"\bProxmox\b",
    "Scale_Computing": r"Scale[\s_]?Computing",
    "NetApp": r"\bNetApp\b",
    "Huawei": r"\bHuawei\b|FusionCube",
    "IBM": r"\bIBM\b",
    "Cisco": r"\bCisco\b",
    "Rubrik": r"\bRubrik\b",
    "Qumulo": r"\bQumulo\b",
    "VAST_Data": r"\bVAST\b",
    "StorMagic": r"\bStorMagic\b",
    "Oracle": r"\bOracle\b|ZFS\b",
    "Scality": r"\bScality\b",
    "Veeam": r"\bVeeam\b",
}

# ─────────────────────────────────────────────────────────────────────
# ENTITY DICTIONARIES — Nutanix products
# ─────────────────────────────────────────────────────────────────────
NUTANIX_PRODUCTS: Dict[str, str] = {
    "AOS": r"\bAOS\b",
    "AHV": r"\bAHV\b",
    "Prism": r"\bPrism Central?\b|\bPrism\b",
    "Flow": r"\bFlow Networking\b|\bNutanix Flow\b|Microseg",
    "Calm": r"\bNutanix Calm\b|Calm\b",
    "Karbon": r"\bKarbon\b",
    "NKP": r"\b(NKP|Nutanix Kubernetes Platform)\b",
    "NDB": r"\b(NDB|Nutanix Database Service|Nutanix Database)\b",
    "Files": r"\bNutanix Files\b",
    "Objects": r"\bNutanix Objects\b",
    "LCM": r"\bLCM\b",
    "Foundation": r"\bFoundation\b",
    "v4_API": r"\bv4 API\b|v4-api",
    "NCI": r"\bNCI\b",
    "NC2": r"\bNC2\b|Cloud Clusters on Azure",
    "Mine": r"\bNutanix Mine\b",
    "Beam": r"\bBeam\b",
    "Era": r"\bEra\b",
    "Move": r"\bNutanix Move\b",
    "Xpress": r"\bXpress\b",
    "Nutanix_Central": r"\bNutanix Central\b",
    "IAM": r"\bIAM\b",
    "Vanguard": r"\bVanguard\b",
    "Security_Central": r"\bSecurity Central\b",
    "NCC": r"\bNCC\b",
}

# ─────────────────────────────────────────────────────────────────────
# PATH TAXONOMY
# ─────────────────────────────────────────────────────────────────────

# Folders whose contents are internal (not for NX_Shield)
INTERNAL_FOLDERS: set = {
    "slack", "whatsapp", "internal", "google-docs",
    "inbound", "jeroentielen.nl", "juliendumur",
}

# Top-level folder → doc_type mapping
DOC_TYPE_MAP: Dict[str, str] = {
    "portal": "official_doc",
    "kb_articles": "kb_article",
    "xpress-md": "battlecard",
    "xpress-downloads": "battlecard",
    "scraped": "web_capture",
    "slack": "team_chat",
    "whatsapp": "team_chat",
    "google-docs": "intelligence",
    "broadcom-vmware": "competitive_intel",
    "github": "code_repo",
    "enablement-essentials": "enablement",
    "gts-2026": "enablement",
    "docs": "official_doc",
    "nutanix.dev": "tech_blog",
    "developers.nutanix.com": "api_spec",
    "downloads": "official_doc",
    "hardware": "reference",
    "terraform": "code_repo",
    "pdfs": "official_doc",
}

# Portal subdirectory → primary_product mapping (complete)
PORTAL_PRODUCT_MAP: Dict[str, str] = {
    "aos": "AOS",
    "ahv": "AHV",
    "prism": "Prism",
    "prism_central": "Prism",
    "nutanix_database_service": "NDB",
    "files": "Files",
    "objects": "Objects",
    "nkp": "NKP",
    "nutanix_kubernetes_platform": "NKP",
    "nutanix_kubernetes_engine": "NKE",
    "lcm": "LCM",
    "ncc": "NCC",
    "flow_(standalone_mode)": "Flow",
    "flow_network_security_next-gen": "Flow",
    "flow_virtual_networking": "Flow",
    "legacy_flow_network_security": "Flow",
    "move": "Move",
    "cloud_clusters_nc2": "NC2",
    "cloud_clusters_(nc2)": "NC2",
    "nutanix_central": "Nutanix_Central",
    "nutanix_enterprise_ai": "NCI",
    "security_advisories": "AOS",
    "aos_security": "AOS",
    "foundation": "Foundation",
    "foundation_central": "Foundation",
    "nutanix_disaster_recovery": "DR",
    "pdbased_dr": "DR",
    "pd-based_dr": "DR",
    "dras": "DR",
    "self-service": "Calm",
    "licensing": "General",
    "nutanix_cloud_manager": "NCM",
    "cost_governance": "NCM",
    "data_lens": "NCM",
    "collector": "NCM",
    "intelligent_operations": "AIOps",
    "nutanix_data_services_for_kubernetes": "NDK",
    "ncp_with_dell_powerflex": "NC2",
    "ncp_with_everpure_flasharray": "NC2",
    "file_analytics": "Files",
    "nutanix_konnector": "Flow",
    "catchall": "General",
    "solutions": "General",
    "kb_articles": "General",
    "nutanix_validated_designs": "NVD",
    "hardware": "General",
    "volumes": "AOS",
    "dark_site": "AOS",
    "nutanix_marketplace": "Calm",
    "nutanix_cloud_security": "AOS",
    "security_central": "Security_Central",
    "compatibility_matrix": "General",
    "config_maximums": "General",
    "niva": "NCI",
    "x-ray": "X-Ray",
    "glossary": "General",
    "api_reference": "v4_API",
    "developers_nutanix_com": "v4_API",
    "nutanix_portal_dell_compat": "General",
    "nutanix_bible": "General",
    "catchall": "General",
}


def get_access_level(rel_path: str) -> str:
    """Determine if a document's content is public or internal."""
    parts = rel_path.split("/")
    top = parts[0] if parts else ""
    return "internal" if top in INTERNAL_FOLDERS else "public"


def get_doc_type(rel_path: str) -> str:
    """Map top-level folder to document type."""
    parts = rel_path.split("/")
    top = parts[0] if parts else ""
    path_lower = rel_path.lower()

    # Check explicit mapping first
    if top in DOC_TYPE_MAP:
        return DOC_TYPE_MAP[top]

    # Detect nested API specs
    if "api_specs" in path_lower or "api_reference" in path_lower:
        return "api_spec"

    # Detect blog content
    if "blog" in path_lower:
        return "tech_blog"

    return "official_doc"


def get_primary_product(rel_path: str) -> str:
    """Map portal subdirectory to primary product. Falls back to 'General'."""
    parts = rel_path.split("/")
    path_lower = rel_path.lower()

    # Check for known portal subdirectory
    for key, product in PORTAL_PRODUCT_MAP.items():
        if key in path_lower:
            return product

    # Top-level folder hints
    top = parts[0] if parts else ""
    if top == "xpress-md" or top == "xpress-downloads":
        return "Competitive"
    if top == "broadcom-vmware":
        return "Competitive"
    if top == "developers.nutanix.com":
        return "v4_API"

    return "General"


# ─────────────────────────────────────────────────────────────────────
# ENTITY EXTRACTION (Regex-based, secondary)
# ─────────────────────────────────────────────────────────────────────

def extract_mentioned_products(text: str) -> List[str]:
    """Find all Nutanix products mentioned in text (no limit)."""
    found = set()
    for name, pattern in NUTANIX_PRODUCTS.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.add(name)
    return sorted(found)


def extract_ecosystem_entities(text: str) -> List[str]:
    """Find all ecosystem/competitor entities mentioned in text."""
    found = set()
    for name, pattern in ECOSYSTEM_ENTITIES.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.add(name)
    return sorted(found)


def extract_versions(text: str) -> List[str]:
    """Extract version strings from text."""
    versions: List[str] = []
    patterns = {
        "AOS": r"\bAOS\s+(\d+\.\d+(?:\.\d+)?)\b",
        "AHV": r"\bAHV\s+(\d+\.\d+(?:\.\d+)?)\b",
        "Prism_Central": r"\bPrism Central\s+(\d+\.\d+(?:\.\d+)?)\b|PC\s+(\d+\.\d+)",
        "NKP": r"\bNKP\s+(\d+\.\d+)\b",
        "NDB": r"\bNDB\s+(\d+\.\d+)\b",
        "Files": r"\bFiles\s+(\d+\.\d+)\b",
        "Objects": r"\bObjects\s+(\d+\.\d+)\b",
    }
    for product, pattern in patterns.items():
        matches = re.findall(pattern, text)
        for m in matches:
            ver = m[0] if isinstance(m, tuple) else m
            versions.append(f"{product}_{ver}")
    return list(dict.fromkeys(versions))[:5]


def extract_content_types(text: str, rel_path: str) -> List[str]:
    """Detect content types from text content and path."""
    content_types: List[str] = []
    path_lower = rel_path.lower()

    if "security_advisory" in path_lower or "security_advisories" in path_lower:
        return ["security-advisory"]

    patterns = {
        "api-reference": r"(API\b|SDK\b|REST|endpoint)",
        "troubleshooting": r"(error|issue|fix|debug|troubleshoot|KB\b|knowledge base)",
        "release-notes": r"(release\b|GA\s|EOSL|EOL\b|announced)",
        "faq": r"\bFAQ\b",
        "architecture": r"(architect|design|diagram|topology)",
        "presentation": r"(slide|deck|webinar|presentation)",
    }
    for ctype, pattern in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            content_types.append(ctype)

    if "faq" in path_lower:
        content_types.append("faq")
    if "release" in path_lower:
        content_types.append("release-notes")
    if "battlecard" in path_lower or "compete" in path_lower:
        content_types.append("competitive-intelligence")

    return list(dict.fromkeys(content_types))


# ─────────────────────────────────────────────────────────────────────
# FREQUENCY-BASED PRIMARY TOPIC (fallback for non-portal content)
# ─────────────────────────────────────────────────────────────────────

def get_primary_topic_from_text(text: str) -> str:
    """
    Count product mentions in the text and return the most frequent one.
    Only used as fallback when path-based primary_product returns 'General'.
    """
    counts: Dict[str, int] = {}
    for name, pattern in NUTANIX_PRODUCTS.items():
        matches = len(re.findall(pattern, text, re.IGNORECASE))
        if matches > 0:
            counts[name] = matches
    if counts:
        return max(counts, key=counts.get)
    return ""


# ─────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

def apply_v3_tags(text: str, rel_path: str) -> Dict[str, object]:
    """
    Apply V3 tagging to a single chunk.

    Args:
        text: The chunk text content.
        rel_path: Relative file path (e.g. "portal/prism/guide.md").

    Returns:
        dict with keys matching the V3 LanceDB schema:
            access_level, doc_type, primary_product,
            mentioned_products, ecosystem_entities,
            versions, content_types
    """
    primary_product = get_primary_product(rel_path)

    # If path-based product returns "General", try frequency-based fallback
    if primary_product == "General":
        freq_topic = get_primary_topic_from_text(text)
        if freq_topic:
            primary_product = freq_topic

    return {
        "access_level": get_access_level(rel_path),
        "doc_type": get_doc_type(rel_path),
        "primary_product": primary_product,
        "mentioned_products": extract_mentioned_products(text),
        "ecosystem_entities": extract_ecosystem_entities(text),
        "versions": extract_versions(text),
        "content_types": extract_content_types(text, rel_path),
    }


# ─────────────────────────────────────────────────────────────────────
# INTROSPECTION
# ─────────────────────────────────────────────────────────────────────

def describe() -> Dict:
    """Return a description of mappings for debugging."""
    return {
        "nutanix_products": list(NUTANIX_PRODUCTS.keys()),
        "ecosystem_entities": list(ECOSYSTEM_ENTITIES.keys()),
        "internal_folders": sorted(INTERNAL_FOLDERS),
        "doc_type_map": {k: v for k, v in sorted(DOC_TYPE_MAP.items())},
        "portal_product_map_count": len(PORTAL_PRODUCT_MAP),
    }
