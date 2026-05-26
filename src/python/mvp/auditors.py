# mvp/auditors.py — shim; removed in cleanup commit
from mvp.corpus.auditors import *  # noqa: F401,F403
from mvp.corpus.auditors import (
    CitationLevel, MilestoneInfo, RefsDecl,
    StructureAuditReport, ReferenceAuditReport,
    Auditor, StructureAuditor, ReferenceAuditor,
)
