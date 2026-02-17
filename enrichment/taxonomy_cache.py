"""Load taxonomy tables once at startup into in-memory structures (plan rule 2). No per-batch queries."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from enrichment.db import get_engine
from enrichment.models import (
    EducationLevel,
    EducationType,
    GptQuestion,
    GptQuestionsGroup,
    MacroSectorCopy,
    MicroSectorCopy,
    SeniorityLevel,
)


@dataclass
class SectorMicro:
    id: int
    macro_sector_id: Optional[int]
    name: Optional[str]
    keywords: Optional[str]


@dataclass
class SectorMacro:
    id: int
    name: Optional[str]


@dataclass
class SeniorityEntry:
    id: int
    code: Optional[str]  # kept for compatibility; use normalized_label
    name: Optional[str]
    collar_scope: Optional[str] = None
    level_rank: Optional[int] = None
    normalized_label: Optional[str] = None


@dataclass
class EducationLevelEntry:
    id: int
    code: Optional[str]  # kept for compatibility; use normalized_label
    name: Optional[str]
    level_rank: Optional[int] = None
    normalized_label: Optional[str] = None


@dataclass
class EducationTypeEntry:
    id: int
    normalized_name: Optional[str]
    name: Optional[str]


@dataclass
class GptGroupEntry:
    id: int
    name: Optional[str]
    description: Optional[str]


@dataclass
class GptQuestionEntry:
    id: int
    gpt_questions_groups_id: Optional[int]
    name: Optional[str]
    keywords: Optional[str]
    description: Optional[str]


@dataclass
class TaxonomyCache:
    """In-memory cache of all taxonomy tables. Load once at pipeline startup."""

    macro_sectors: list[SectorMacro] = field(default_factory=list)
    micro_sectors: list[SectorMicro] = field(default_factory=list)
    gpt_groups: list[GptGroupEntry] = field(default_factory=list)
    gpt_questions: list[GptQuestionEntry] = field(default_factory=list)
    seniority_levels: list[SeniorityEntry] = field(default_factory=list)
    education_levels: list[EducationLevelEntry] = field(default_factory=list)
    education_types: list[EducationTypeEntry] = field(default_factory=list)

    # Lookup by id
    macro_by_id: dict[int, SectorMacro] = field(default_factory=dict)
    micro_by_id: dict[int, SectorMicro] = field(default_factory=dict)
    gpt_group_by_id: dict[int, GptGroupEntry] = field(default_factory=dict)
    gpt_question_by_id: dict[int, GptQuestionEntry] = field(default_factory=dict)
    seniority_by_id: dict[int, SeniorityEntry] = field(default_factory=dict)
    seniority_by_code: dict[str, int] = field(default_factory=dict)  # code -> id
    seniority_by_name: dict[str, int] = field(default_factory=dict)  # normalized name -> id
    # normalized_label (normalized) -> list of (collar_scope, id) for collar-aware lookup
    seniority_by_normalized_label: dict[str, list[tuple[Optional[str], int]]] = field(default_factory=dict)
    education_level_by_id: dict[int, EducationLevelEntry] = field(default_factory=dict)
    education_level_by_code: dict[str, int] = field(default_factory=dict)  # code -> id
    education_level_by_name: dict[str, int] = field(default_factory=dict)  # normalized name -> id
    education_level_by_normalized_label: dict[str, int] = field(default_factory=dict)  # normalized_label -> id
    education_type_by_id: dict[int, EducationTypeEntry] = field(default_factory=dict)
    education_type_by_normalized_name: dict[str, int] = field(default_factory=dict)  # normalized_name -> id

    def get_macro_for_micro(self, micro_id: int) -> Optional[SectorMacro]:
        micro = self.micro_by_id.get(micro_id)
        if not micro or micro.macro_sector_id is None:
            return None
        return self.macro_by_id.get(micro.macro_sector_id)

    def get_gpt_group_for_question(self, question_id: int) -> Optional[GptGroupEntry]:
        q = self.gpt_question_by_id.get(question_id)
        if not q or q.gpt_questions_groups_id is None:
            return None
        return self.gpt_group_by_id.get(q.gpt_questions_groups_id)

    def get_seniority_id_by_code(self, code: str) -> Optional[int]:
        return self.seniority_by_code.get(code)

    def get_seniority_id_by_code_or_name(
        self, code: str, collar_type: Optional[str] = None
    ) -> Optional[int]:
        sid = self.seniority_by_code.get(code)
        if sid is not None:
            return sid
        # Prefer lookup by normalized_label with collar_scope match
        norm_key = _normalize_name_for_lookup(code)
        if norm_key:
            candidates = self.seniority_by_normalized_label.get(norm_key, [])
            if candidates:
                # Prefer id whose collar_scope equals collar_type
                for scope, lid in candidates:
                    if scope and collar_type and scope == collar_type:
                        return lid
                # Else accept collar_scope None or "all"
                for scope, lid in candidates:
                    if not scope or (isinstance(scope, str) and scope.lower() == "all"):
                        return lid
                # Else first available
                return candidates[0][1]
        # Fallback: SENIORITY_CODE_TO_NAMES + seniority_by_name
        for name in SENIORITY_CODE_TO_NAMES.get(code, []):
            key = _normalize_name_for_lookup(name)
            if key:
                sid = self.seniority_by_name.get(key)
                if sid is not None:
                    return sid
        return None

    def get_education_level_id_by_code(self, code: str) -> Optional[int]:
        return self.education_level_by_code.get(code)

    def get_education_level_id_by_code_or_name(self, code: str) -> Optional[int]:
        lid = self.education_level_by_code.get(code)
        if lid is not None:
            return lid
        # Prefer lookup by normalized_label
        norm_key = _normalize_name_for_lookup(code)
        if norm_key:
            lid = self.education_level_by_normalized_label.get(norm_key)
            if lid is not None:
                return lid
        # Fallback: EDUCATION_LEVEL_CODE_TO_NAMES + education_level_by_name
        for name in EDUCATION_LEVEL_CODE_TO_NAMES.get(code, []):
            key = _normalize_name_for_lookup(name)
            if key:
                lid = self.education_level_by_name.get(key)
                if lid is not None:
                    return lid
        return None

    def get_education_type_id_by_normalized_name(self, name: str) -> Optional[int]:
        return self.education_type_by_normalized_name.get(name)


logger = logging.getLogger("enrichment")

_TABLE_MISSING_CODES = (1146,)  # MySQL: table doesn't exist

# Code (from regex) -> possible DB name variants for lookup when 'code' column is missing
SENIORITY_CODE_TO_NAMES: dict[str, list[str]] = {
    "internship": ["internship", "stage", "tirocinio"],
    "apprenticeship": ["apprenticeship", "apprendistato"],
    "entry_level": ["entry level", "entry-level"],
    "junior": ["junior"],
    "mid_level": ["mid level", "mid-level", "middle", "medio"],
    "senior": ["senior", "esperto"],
    "manager": ["manager", "responsabile", "capo turno", "team leader"],
}
EDUCATION_LEVEL_CODE_TO_NAMES: dict[str, list[str]] = {
    "none_required": ["nessun titolo", "non richiesto", "no title"],
    "middle_school": ["licenza media", "scuola media", "middle school"],
    "vocational_qualification": ["qualifica professionale", "qualification", "qualifica"],
    "high_school_diploma": ["diploma", "high school", "diploma superiore"],
    "its_ifts": ["its", "ifts"],
    "bachelor": ["laurea triennale", "bachelor", "triennale"],
    "master_degree": ["laurea magistrale", "master", "magistrale"],
    "mba": ["mba"],
    "phd": ["phd", "dottorato", "doctorate"],
}


def _normalize_name_for_lookup(name: Optional[str]) -> str:
    """Lowercase, strip, replace - and _ with space. For building by_name maps."""
    if not name:
        return ""
    s = (name or "").strip().lower()
    for c in "-_":
        s = s.replace(c, " ")
    return " ".join(s.split())


def _load_table(session, select_stmt, table_name: str):
    """Execute select and return list of rows. On missing table, log and return []."""
    try:
        return list(session.execute(select_stmt).scalars().all())
    except (ProgrammingError, OperationalError) as e:
        code = getattr(getattr(e, "orig", None), "errno", None) or getattr(e, "errno", None)
        if code in _TABLE_MISSING_CODES or "doesn't exist" in str(e).lower():
            logger.warning("Taxonomy table %s not found; using empty cache for it.", table_name)
            return []
        raise

def load_taxonomy_cache() -> TaxonomyCache:
    """Load all taxonomy tables once. Call at pipeline startup only (plan rule 2). Missing tables are skipped with empty data."""
    from enrichment.db import session_scope

    cache = TaxonomyCache()
    with session_scope() as session:
        # Macro sectors
        for r in _load_table(session, select(MacroSectorCopy), "macro_sector_copy"):
            e = SectorMacro(id=r.id, name=r.name)
            cache.macro_sectors.append(e)
            cache.macro_by_id[r.id] = e

        # Micro sectors
        for r in _load_table(session, select(MicroSectorCopy), "micro_sector_copy"):
            e = SectorMicro(
                id=r.id,
                macro_sector_id=r.macro_id,
                name=r.name,
                keywords=r.keywords,
            )
            cache.micro_sectors.append(e)
            cache.micro_by_id[r.id] = e

        # White collar: gpt_questions_groups (macro) and gpt_questions (micro)
        for r in _load_table(session, select(GptQuestionsGroup), "gpt_questions_groups"):
            e = GptGroupEntry(id=r.id, name=r.name, description=r.description)
            cache.gpt_groups.append(e)
            cache.gpt_group_by_id[r.id] = e

        for r in _load_table(session, select(GptQuestion), "gpt_questions"):
            e = GptQuestionEntry(
                id=r.id,
                gpt_questions_groups_id=r.gpt_questions_groups_id,
                name=r.name,
                keywords=r.keywords,
                description=r.description,
            )
            cache.gpt_questions.append(e)
            cache.gpt_question_by_id[r.id] = e

        # Seniority levels: normalized_label, collar_scope, level_rank
        seniority_rows = _load_table(session, select(SeniorityLevel), "seniority_levels")
        for r in seniority_rows:
            code = getattr(r, "code", None)
            collar_scope = getattr(r, "collar_scope", None)
            level_rank = getattr(r, "level_rank", None)
            normalized_label = getattr(r, "normalized_label", None)
            e = SeniorityEntry(
                id=r.id, code=code, name=r.name,
                collar_scope=collar_scope, level_rank=level_rank, normalized_label=normalized_label,
            )
            cache.seniority_levels.append(e)
            cache.seniority_by_id[r.id] = e
            if code:
                cache.seniority_by_code[code] = r.id
            if r.name:
                key = _normalize_name_for_lookup(r.name)
                if key:
                    cache.seniority_by_name[key] = r.id
            if normalized_label:
                nkey = _normalize_name_for_lookup(normalized_label)
                if nkey:
                    if nkey not in cache.seniority_by_normalized_label:
                        cache.seniority_by_normalized_label[nkey] = []
                    cache.seniority_by_normalized_label[nkey].append((collar_scope, r.id))
        cache.seniority_levels.sort(key=lambda x: (x.level_rank is None, x.level_rank or 0))

        # Education levels: normalized_label, level_rank
        education_rows = _load_table(session, select(EducationLevel), "education_levels")
        for r in education_rows:
            code = getattr(r, "code", None)
            level_rank = getattr(r, "level_rank", None)
            normalized_label = getattr(r, "normalized_label", None)
            e = EducationLevelEntry(
                id=r.id, code=code, name=r.name,
                level_rank=level_rank, normalized_label=normalized_label,
            )
            cache.education_levels.append(e)
            cache.education_level_by_id[r.id] = e
            if code:
                cache.education_level_by_code[code] = r.id
            if r.name:
                key = _normalize_name_for_lookup(r.name)
                if key:
                    cache.education_level_by_name[key] = r.id
            if normalized_label:
                nkey = _normalize_name_for_lookup(normalized_label)
                if nkey and nkey not in cache.education_level_by_normalized_label:
                    cache.education_level_by_normalized_label[nkey] = r.id
        cache.education_levels.sort(key=lambda x: (x.level_rank is None, x.level_rank or 0))

        # Education types
        for r in _load_table(session, select(EducationType), "education_types"):
            e = EducationTypeEntry(
                id=r.id,
                normalized_name=r.normalized_name,
                name=r.name,
            )
            cache.education_types.append(e)
            cache.education_type_by_id[r.id] = e
            if r.normalized_name:
                cache.education_type_by_normalized_name[r.normalized_name] = r.id

    return cache
