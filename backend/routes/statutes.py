import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from models.database import get_db, Act, Provision, StatuteMapping, IngestionLog
from services.indiacode_ingest import IngestionService, IndiaCodeAPIError

logger = logging.getLogger("LexSetu.StatutesRouter")
router = APIRouter()
ingest_service = IngestionService()


@router.get("/meta", summary="Statute corpus metadata & source authority")
def get_corpus_meta(db: Session = Depends(get_db)):
    """
    Returns repository corpus counts, source authority attribution, and API status.
    Explicitly separates source API from official canonical source.
    """
    try:
        api_meta = ingest_service.client.get_meta()
        remote_corpus = api_meta.get("data", {}).get("corpus", {})
        build_info = api_meta.get("data", {}).get("build")
        corpus_date = api_meta.get("data", {}).get("corpus_date")
    except Exception as e:
        logger.warning(f"Live meta fetch failed: {e}")
        remote_corpus = {}
        build_info = None
        corpus_date = None

    db_acts_count = db.query(Act).count()
    db_provisions_count = db.query(Provision).count()
    db_mappings_count = db.query(StatuteMapping).count()

    return {
        "status": "online",
        "source_api": ingest_service.client.source_api,
        "source_type": "INDIA_CODE_API",
        "source_authority": "INDIA_CODE_CORPUS",
        "attribution_note": (
            "Statute data is republished from the India Code API (by eCourtsIndia). "
            "Canonical legislative records originate from indiacode.gov.in."
        ),
        "local_storage": {
            "acts_stored": db_acts_count,
            "provisions_indexed": db_provisions_count,
            "mappings_stored": db_mappings_count,
        },
        "remote_corpus": remote_corpus,
        "build": build_info,
        "corpus_date": corpus_date,
    }


@router.get("/acts", summary="List and filter stored Acts")
def list_acts(
    q: Optional[str] = Query(None, description="Search term for title or act number"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction (e.g. CENTRAL)"),
    in_force: Optional[bool] = Query(None, description="Filter by in_force status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    Paginated listing of Acts in the local structured database.
    Does not load the entire corpus into memory; queries only requested page.
    """
    query = db.query(Act)

    if q:
        search_filter = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Act.title.ilike(search_filter),
                Act.source_act_id.ilike(search_filter),
                Act.act_number.ilike(search_filter),
            )
        )

    if jurisdiction:
        query = query.filter(Act.jurisdiction.ilike(f"%{jurisdiction.strip()}%"))

    if in_force is not None:
        query = query.filter(Act.in_force == in_force)

    total = query.count()
    offset = (page - 1) * limit
    acts = query.order_by(Act.year.desc().nullslast(), Act.title.asc()).offset(offset).limit(limit).all()

    items = []
    for act in acts:
        items.append({
            "id": act.id,
            "source_act_id": act.source_act_id,
            "title": act.title,
            "long_title": act.long_title,
            "year": act.year,
            "act_number": act.act_number,
            "ministry": act.ministry,
            "department": act.department,
            "jurisdiction": act.jurisdiction,
            "unit": act.unit,
            "section_count": act.section_count,
            "in_force": act.in_force,
            "source_url": act.source_url,
            "source_api": act.source_api,
            "source_type": act.source_type,
            "source_authority": act.source_authority,
            "retrieved_at": act.retrieved_at.isoformat() if act.retrieved_at else None,
            "raw_response_sha256": act.raw_response_sha256,
            "content_sha256": act.content_sha256,
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if limit > 0 else 0,
        "acts": items,
    }


@router.get("/acts/{act_id}", summary="Get Act metadata and its provisions index")
def get_act_detail(
    act_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves single Act details along with its index of provisions.
    """
    clean_id = act_id.strip().lower()
    act = db.query(Act).filter(
        or_(Act.source_act_id == clean_id, Act.id == clean_id)
    ).first()

    if not act:
        raise HTTPException(status_code=404, detail=f"Act '{act_id}' not found in database.")

    provisions = db.query(Provision).filter(
        Provision.act_source_id == act.source_act_id
    ).all()

    # Sort provisions sensibly: numeric if possible, alphanumeric in order
    def sort_key(p):
        num_str = p.provision_number
        digits = "".join([c for c in num_str if c.isdigit()])
        suffix = "".join([c for c in num_str if not c.isdigit()])
        val = int(digits) if digits else 0
        return (val, suffix)

    sorted_provisions = sorted(provisions, key=sort_key)

    provision_stubs = [
        {
            "id": p.id,
            "provision_number": p.provision_number,
            "heading": p.heading,
            "title": p.heading,
            "words": p.words,
            "has_text": p.raw_text is not None,
            "source_url": p.source_url,
        }
        for p in sorted_provisions
    ]

    return {
        "act": {
            "id": act.id,
            "source_act_id": act.source_act_id,
            "title": act.title,
            "long_title": act.long_title,
            "year": act.year,
            "act_number": act.act_number,
            "ministry": act.ministry,
            "department": act.department,
            "jurisdiction": act.jurisdiction,
            "unit": act.unit,
            "section_count": act.section_count,
            "in_force": act.in_force,
            "source_url": act.source_url,
            "source_api": act.source_api,
            "source_type": act.source_type,
            "source_authority": act.source_authority,
            "retrieved_at": act.retrieved_at.isoformat() if act.retrieved_at else None,
            "raw_response_sha256": act.raw_response_sha256,
            "content_sha256": act.content_sha256,
        },
        "provisions_count": len(provision_stubs),
        "provisions": provision_stubs,
    }


@router.get("/acts/{act_id}/provisions/{provision_number}", summary="Exact provision lookup with verbatim text & correspondences")
def get_exact_provision(
    act_id: str,
    provision_number: str,
    db: Session = Depends(get_db),
):
    """
    Exact statutory provision lookup:
    Act -> Provision -> Exact verbatim text.
    Uses structured database lookup. If text is not yet stored, safely fetches from source API.
    Does NOT use vector search. Never alters legal text. Never fabricates missing fields.
    """
    clean_id = act_id.strip().lower()
    clean_num = str(provision_number).strip()

    # Resolve Act by source_act_id or id UUID
    act = db.query(Act).filter(
        or_(Act.source_act_id == clean_id, Act.id == clean_id)
    ).first()
    clean_act = act.source_act_id if act else clean_id

    # Lookup or sync provision
    try:
        provision = ingest_service.get_or_fetch_provision(clean_act, clean_num, db)
    except IndiaCodeAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Section '{clean_num}' of '{clean_act}' not found from source."
            )
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve source data."
        )
    except Exception as e:
        logger.error(f"Error retrieving provision {clean_act}/{clean_num}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve source data."
        )

    if not provision:
        raise HTTPException(
            status_code=404,
            detail=f"Section '{clean_num}' of '{clean_act}' not found from source."
        )

    if not act:
        act = db.query(Act).filter(Act.source_act_id == clean_act).first()

    # Query source mappings (bidirectional)
    mappings = db.query(StatuteMapping).filter(
        or_(
            and_(StatuteMapping.from_act == clean_act, StatuteMapping.from_provision == clean_num),
            and_(StatuteMapping.to_act == clean_act, StatuteMapping.to_provision == clean_num),
        )
    ).all()

    correspondences = []
    for m in mappings:
        if m.from_act == clean_act and m.from_provision == clean_num:
            direction = "successor" if m.pair in ("ipc-bns", "crpc-bnss", "iea-bsa") else "counterpart"
            target_act = m.to_act
            target_sec = m.to_provision
            target_heading = m.to_heading
            target_url = m.to_url
        else:
            direction = "predecessor"
            target_act = m.from_act
            target_sec = m.from_provision
            target_heading = m.from_heading
            target_url = m.from_url

        correspondences.append({
            "direction": direction,
            "pair": m.pair,
            "target_act": target_act,
            "target_provision": target_sec,
            "target_heading": target_heading,
            "relation": m.relation,
            "score": m.score,
            "target_url": target_url,
            "label": "Source-listed correspondence (API mapping)",
            "applicability_warning": "Source mapping only; legal applicability depends on case timeline and procedural posture.",
        })

    formatted_correspondences = []
    for c in correspondences:
        formatted_correspondences.append({
            **c,
            "target_act_code": c["target_act"].upper(),
            "target_section": c["target_provision"],
            "mapping_type": c.get("relation") or c.get("direction") or "CORRESPONDING",
            "description": f"{c.get('target_heading', '')} ({c.get('direction', '')})",
        })

    return {
        "id": provision.id,
        "act_id": act.id if act else provision.act_source_id,
        "act_source_id": provision.act_source_id,
        "act_title": act.title if act else provision.act_source_id.upper(),
        "provision_type": provision.provision_type or "section",
        "provision_number": provision.provision_number,
        "heading": provision.heading or "Not available from source",
        "title": provision.heading or f"Section {provision.provision_number}",
        "content": provision.raw_text,
        "verbatim_text": provision.raw_text,
        "html": provision.html,
        "words": provision.words,
        "correspondences": formatted_correspondences,
        "source_correspondences": correspondences,
        "provenance": {
            "source_api": provision.source_api or "indiacode.ecourtsindia.com",
            "canonical_legal_source": provision.source_url,
            "source_type": provision.source_type or "INDIA_CODE_API",
            "source_authority": provision.source_authority or "INDIA_CODE_CORPUS",
            "retrieved_at": provision.retrieved_at.isoformat() if provision.retrieved_at else None,
            "raw_response_sha256": provision.raw_response_sha256,
            "content_sha256": provision.content_sha256,
        },
    }


@router.get("/mappings", summary="Search and filter statutory transition correspondences")
def list_mappings(
    pair: Optional[str] = Query(None, description="e.g. ipc-bns, crpc-bnss, iea-bsa"),
    from_act: Optional[str] = Query(None, description="e.g. ipc"),
    to_act: Optional[str] = Query(None, description="e.g. bns"),
    section: Optional[str] = Query(None, description="Section number to match on either side"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Exposes transition mappings strictly as source-listed correspondences.
    Neutral UI wording; not an automatic conclusion of legal applicability.
    """
    query = db.query(StatuteMapping)

    if pair:
        query = query.filter(StatuteMapping.pair == pair.strip().lower())
    if from_act:
        query = query.filter(StatuteMapping.from_act == from_act.strip().lower())
    if to_act:
        query = query.filter(StatuteMapping.to_act == to_act.strip().lower())
    if section:
        sec = section.strip()
        query = query.filter(
            or_(StatuteMapping.from_provision == sec, StatuteMapping.to_provision == sec)
        )

    total = query.count()
    offset = (page - 1) * limit
    results = query.offset(offset).limit(limit).all()

    items = []
    for m in results:
        items.append({
            "id": m.id,
            "pair": m.pair,
            "from_act": m.from_act,
            "from_provision": m.from_provision,
            "from_heading": m.from_heading,
            "to_act": m.to_act,
            "to_provision": m.to_provision,
            "to_heading": m.to_heading,
            "relation": m.relation,
            "score": m.score,
            "from_url": m.from_url,
            "to_url": m.to_url,
            "label": "Source-listed correspondence",
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "mappings": items,
    }


@router.post("/sync", summary="Trigger dynamic discovery and statutory ingestion")
def trigger_sync(db: Session = Depends(get_db)):
    """
    Runs idempotent ingestion for the required criminal & evidence statutes:
    BNS, BNSS, BSA, IPC, CrPC, and IEA.
    """
    try:
        summary = ingest_service.run_full_initial_ingestion(db)
        return summary
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statute ingestion failed: {e}")
