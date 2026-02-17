"""Step 6: extract education level and education types (multi-value). Insert education_types if missing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from enrichment.llm import call_openai_chat, llm_budget_exhausted
from enrichment.models import EducationType
from enrichment.taxonomy_cache import EducationTypeEntry, TaxonomyCache

# Level patterns -> code (must match education_levels.code or name in DB)
EDUCATION_LEVEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnessun\s+titolo\b|\bno\s+title\b|non\s+richiest[oa]\b", re.I), "none_required"),
    (re.compile(r"\blicenza\s+media\b|\bscuola\s+media\b", re.I), "middle_school"),
    (re.compile(r"\bqualifica\b|\bqualification\b", re.I), "vocational_qualification"),
    (re.compile(r"\bdiploma\b|\bhigh\s+school\b", re.I), "high_school_diploma"),
    (re.compile(r"\bITS\b|\bIFTS\b", re.I), "its_ifts"),
    (re.compile(r"\blaurea\s+triennale\b|\bbachelor\b|\bthree.year\b", re.I), "bachelor"),
    (re.compile(r"\blaurea\s+magistrale\b|\bmaster\b|\bmagistrale\b", re.I), "master_degree"),
    (re.compile(r"\bMBA\b", re.I), "mba"),
    (re.compile(r"\bphd\b|\bdottorato\b|\bdoctorate\b", re.I), "phd"),
]

# Default education level code when no rule/LLM match (by collar)
DEFAULT_EDUCATION_LEVEL_CODE_BLUE = "none_required"
DEFAULT_EDUCATION_LEVEL_CODE_WHITE = "bachelor"

# Education type patterns by collar: (pattern, normalized_name, evidence)
BLUE_EDUCATION_TYPE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bpatente\b|\bpatenti\b|\bdriving\s+licen[cs]e\b", re.I), "patenti", "patente/patenti"),
    (re.compile(r"\bcertificazion[ei]\b|\bcertification\b", re.I), "certificazioni", "certificazione"),
    (re.compile(r"\bpatentino\b|\bpatentini\b", re.I), "patentini", "patentino"),
    (re.compile(r"\bhaccp\b|\bautocontrollo\s+alimentare\b", re.I), "haccp", "haccp"),
    (re.compile(r"\bsicurezza\s+sul\s+lavoro\b|\bD\.?Lgs\.?\s*81\b|\bantincendio\b|\bprimo\s+soccorso\b|\bcorso\s+sicurezza\b", re.I), "sicurezza_lavoro", "sicurezza"),
    (re.compile(r"\bcorso\s+professionale\b|\bformazione\s+professionale\b|\bcorso\s+di\s+formazione\b", re.I), "corsi_professionali", "corso professionale"),
    (re.compile(r"\battestato\b|\battestati\b|\battestati\s+di\s+frequenza\b", re.I), "attestati", "attestato"),
    (re.compile(r"\bqualifica\s+professionale\b|\bqualifica\s+regionale\b", re.I), "qualifica_professionale", "qualifica"),
    (re.compile(r"\babilitazione\b|\babilitato\b|\biscrizione\s+albo\b|\balbo\b", re.I), "abilitazioni", "abilitazione"),
    (re.compile(r"\bapprendistato\b|\bapprendista\b", re.I), "apprendistato", "apprendistato"),
    # Diplomi / scuole superiori (blue collar)
    (re.compile(r"\bragioneri[ae]\b|\bistituto\s+tecnico\s+commerciale\b|\bAFM\b", re.I), "diploma_ragioneria", "ragioneria"),
    (re.compile(r"\bgeometr[ai]\b|\bCAT\b|\bistituto\s+tecnico\s+geometri\b", re.I), "diploma_geometra", "geometra"),
    (re.compile(r"\bperito\b|\bperiti\b|\bistituto\s+tecnico\s+industriale\b", re.I), "diploma_perito", "perito"),
    (re.compile(r"\bdiploma\s+commerciale\b|\bistituto\s+commerciale\b|\btecnico\s+commerciale\b", re.I), "diploma_commerciale", "commerciale"),
    (re.compile(r"\bliceo\b|\bliceali\b|\bliceo\s+(?:classico|scientifico|linguistico|artistico)\b", re.I), "liceo", "liceo"),
    (re.compile(r"\bistituto\s+professionale\b|\bIPSIA\b|\bIPSSAR\b|\balberghiero\b|\bodontotecnico\b", re.I), "istituto_professionale", "istituto professionale"),
]
WHITE_EDUCATION_TYPE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bcertificazion[ei]\b|\bcertification\b", re.I), "certificazioni", "certificazione"),
    (re.compile(r"\bcorso\s+professionale\b|\bformazione\s+professionale\b|\bcorso\s+di\s+formazione\b", re.I), "corsi_professionali", "corso professionale"),
    (re.compile(r"\battestato\b|\battestati\b|\battestati\s+di\s+frequenza\b", re.I), "attestati", "attestato"),
    (re.compile(r"\bspecializzazione\b|\bspecialista\b|\bmaster\s+(?:di\s+)?(?:primo|secondo)\s+livello\b", re.I), "specializzazione", "specializzazione"),
    (re.compile(r"\bqualifica\s+professionale\b|\bqualifica\s+regionale\b", re.I), "qualifica_professionale", "qualifica"),
    # Lauree / ambiti (white collar)
    (re.compile(r"\blaurea\s+in\s+economia\b|\beconomia\s+aziendale\b|\beconomia\s+e\s+commercio\b|\beconomics\b", re.I), "laurea_economia", "economia"),
    (re.compile(r"\b(laurea\s+in\s+)?(matematica|fisica|chimica|biologia|informatica)\b|\bSTEM\b|\bscienze\s+(naturali|matematiche)\b", re.I), "laurea_stem", "STEM"),
    (re.compile(r"\blaurea\s+in\s+ingegneria\b|\bingegnere\b|\bingegneria\s+(civile|meccanica|gestionale|informatica|elettronica)\b", re.I), "laurea_ingegneria", "ingegneria"),
    (re.compile(r"\barchitettura\b|\barchitetto\b|\blaurea\s+in\s+architettura\b", re.I), "laurea_architettura", "architettura"),
    (re.compile(r"\bdesign\s+(industriale|grafico)\b|\bdesigner\b|\bdesign\s+della\s+comunicazione\b", re.I), "laurea_design", "design"),
    (re.compile(r"\bscienze\s+umanistiche\b|\blettere\b|\bfilosofia\b|\bstoria\b|\blingue\b|\bbeni\s+culturali\b|\bhumanities\b", re.I), "laurea_umanistiche", "umanistiche"),
    (re.compile(r"\bgiurisprudenza\b|\blaurea\s+in\s+legge\b|\bgiuridico\b|\bavvocato\b", re.I), "laurea_giuridica", "giuridica"),
    (re.compile(r"\bmedicina\b|\binfermieristica\b|\bfisioterapia\b|\bprofessioni\s+sanitarie\b|\bodontoiatria\b", re.I), "laurea_sanitaria", "sanitaria"),
    (re.compile(r"\bpsicologia\b|\bpsicologo\b|\blaurea\s+in\s+psicologia\b", re.I), "laurea_psicologia", "psicologia"),
]


@dataclass
class EducationTypeRef:
    normalized_name: str
    confidence: float
    evidence: Optional[str] = None


@dataclass
class EducationResult:
    education_level_id: Optional[int]
    education_confidence: float
    education_method: str
    education_types: list[EducationTypeRef]  # multi-value
    explanation: Optional[dict] = None


def extract_level_rule(normalized_text: str, cache: TaxonomyCache) -> Optional[tuple[int, float, str]]:
    """First match wins. Returns (level_id, confidence, method) or None."""
    for pattern, code in EDUCATION_LEVEL_PATTERNS:
        if pattern.search(normalized_text):
            lid = cache.get_education_level_id_by_code_or_name(code)
            if lid is not None:
                return (lid, 0.85, "rule")
    return None


def _valid_education_level_codes(cache: TaxonomyCache) -> list[str]:
    """Codes the LLM may choose from: cache normalized_label/code if any, else our pattern codes."""
    from enrichment.taxonomy_cache import EDUCATION_LEVEL_CODE_TO_NAMES
    from_cache = [
        (e.normalized_label or e.code) for e in cache.education_levels
        if (e.normalized_label or e.code)
    ]
    if from_cache:
        return from_cache
    return list(EDUCATION_LEVEL_CODE_TO_NAMES.keys())


def extract_level_llm(
    normalized_text: str,
    cache: TaxonomyCache,
    collar_type: str = "blue",
) -> Optional[tuple[int, float, str]]:
    if llm_budget_exhausted() or not cache.education_levels:
        return None
    codes = _valid_education_level_codes(cache)
    if not codes:
        return None
    collar_hint = "This is a %s collar job; prefer levels typical for this context." % (
        "white" if collar_type == "white" else "blue"
    )
    prompt = (
        "Choose the minimum education level required. Reply with JSON: {\"code\": \"<code>\"}. "
        "Valid codes: " + ", ".join(codes) + ". " + collar_hint + "\n\nText: " + (normalized_text[:1000] or "")
    )
    out = call_openai_chat([{"role": "user", "content": prompt}], json_mode=True)
    if not out:
        return None
    try:
        data = json.loads(out)
        code = data.get("code", "")
        if code not in codes:
            code = codes[0]
        lid = cache.get_education_level_id_by_code_or_name(code)
        if lid is None:
            lid = cache.education_levels[0].id
        return (lid, 0.70, "llm")
    except (json.JSONDecodeError, TypeError):
        return None


def extract_education_types_rule(normalized_text: str, collar_type: str = "blue") -> list[EducationTypeRef]:
    """Extract education types by collar: blue (patenti, HACCP, sicurezza, ...), white (certificazioni, specializzazione, ...)."""
    refs: list[EducationTypeRef] = []
    t = normalized_text or ""
    patterns = BLUE_EDUCATION_TYPE_PATTERNS if collar_type == "blue" else WHITE_EDUCATION_TYPE_PATTERNS
    for pattern, normalized_name, evidence in patterns:
        if pattern.search(t):
            refs.append(EducationTypeRef(normalized_name, 0.8, evidence))
    return refs


def ensure_education_type(
    session: Session,
    cache: TaxonomyCache,
    normalized_name: str,
) -> int:
    """
    Return education_type id for normalized_name. If not in cache, insert into education_types
    and add to cache (no duplicate by normalized_name).
    """
    n = normalized_name.strip().lower() or "other"
    existing = cache.get_education_type_id_by_normalized_name(n)
    if existing is not None:
        return existing
    row = EducationType(normalized_name=n, name=n)
    session.add(row)
    session.flush()
    entry = EducationTypeEntry(id=row.id, normalized_name=n, name=n)
    cache.education_types.append(entry)
    cache.education_type_by_id[row.id] = entry
    cache.education_type_by_normalized_name[n] = row.id
    return row.id


def extract_education(
    normalized_text: str,
    cache: TaxonomyCache,
    collar_type: str = "blue",
) -> EducationResult:
    """Extract level and types. Does not write to DB; caller uses ensure_education_type when writing."""
    level_id = None
    confidence = 0.5
    method = "default"
    expl: dict = {}

    res = extract_level_rule(normalized_text, cache)
    if res is not None:
        level_id, confidence, method = res
        expl["level_trigger"] = "rule"
    else:
        res = extract_level_llm(normalized_text, cache, collar_type)
        if res is not None:
            level_id, confidence, method = res
            expl["level_trigger"] = "llm"
    if level_id is None and cache.education_levels:
        default_code = DEFAULT_EDUCATION_LEVEL_CODE_WHITE if collar_type == "white" else DEFAULT_EDUCATION_LEVEL_CODE_BLUE
        level_id = cache.get_education_level_id_by_code_or_name(default_code)
        if level_id is None:
            level_id = cache.education_levels[0].id
        expl["level_trigger"] = "default_by_collar"
        expl["default_code"] = default_code

    type_refs = extract_education_types_rule(normalized_text, collar_type)
    return EducationResult(
        education_level_id=level_id,
        education_confidence=confidence,
        education_method=method,
        education_types=type_refs,
        explanation=expl or None,
    )
