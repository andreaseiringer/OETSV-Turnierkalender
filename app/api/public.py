import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException

from app.config import settings
from app.database import get_db_connection
from app.services import storage_service
from app.models import (
    TurnierModel, PaarNennungModel, NennungsKlasseModel, SyncStatusModel,
    TurnierErgebnisModel, TurnierTeilnehmerModel, TurnierTeilnehmerKlasseModel,
    TurnierTeilnehmerListResponse, StorageConfigModel, StorageConfigUpdateModel,
    StorageLockResolveModel
)

router = APIRouter(prefix="/api", tags=["public"])

@router.get("/turniere", response_model=List[TurnierModel])
def get_turniere(only_current_year: bool = Query(default=True, description="Nur Turniere ab aktuellem Kalenderjahr")):
    """Get all tournaments ordered chronologically, always including club registrations."""
    now_vienna = datetime.now(ZoneInfo(settings.TIMEZONE))
    current_year_str = f"{now_vienna.year}-01-01"

    with get_db_connection() as conn:
        cursor = conn.cursor()

        query = """
            SELECT id, turnier_id, datum, datum_sort, titel, klub, bundesland, tags, links
            FROM turniere
        """
        params = []
        if only_current_year:
            query += " WHERE datum_sort >= ?"
            params.append(current_year_str)

        query += " ORDER BY datum_sort ASC, id ASC;"
        cursor.execute(query, params)
        tournament_rows = cursor.fetchall()

        if not tournament_rows:
            return []

        # Load all nennungen for these tournaments
        # Can join by turnier_db_id or turnier_id
        t_ids = [r["id"] for r in tournament_rows]
        t_verband_ids = [r["turnier_id"] for r in tournament_rows if r["turnier_id"] is not None]

        placeholders_id = ",".join("?" for _ in t_ids)
        placeholders_vid = ",".join("?" for _ in t_verband_ids) if t_verband_ids else "NULL"

        nennungen_query = f"""
            SELECT id, nennungs_id, paar_name, min_partner_1, min_partner_2, klub, turnier_id, turnier_db_id
            FROM nennungen
            WHERE turnier_db_id IN ({placeholders_id})
               OR (turnier_db_id IS NULL AND turnier_id IN ({placeholders_vid}));
        """
        nennungen_params = list(t_ids)
        if t_verband_ids:
            nennungen_params.extend(t_verband_ids)

        cursor.execute(nennungen_query, nennungen_params)
        nennung_rows = cursor.fetchall()

        # Load all start classes for fetched nennungen
        nennung_ids = [nr["id"] for nr in nennung_rows]
        klassen_map = {}
        if nennung_ids:
            p_nids = ",".join("?" for _ in nennung_ids)
            cursor.execute(f"""
                SELECT id, nennung_db_id, datum, klasse
                FROM nennungs_klassen
                WHERE nennung_db_id IN ({p_nids})
                ORDER BY datum ASC, id ASC;
            """, nennung_ids)
            for krow in cursor.fetchall():
                nid = krow["nennung_db_id"]
                if nid not in klassen_map:
                    klassen_map[nid] = []
                klassen_map[nid].append(NennungsKlasseModel(
                    id=krow["id"],
                    datum=krow["datum"],
                    klasse=krow["klasse"]
                ))

        # Map nennungen to tournament id and turnier_id
        nennungen_by_tid = {}
        nennungen_by_verband_id = {}

        for nr in nennung_rows:
            model = PaarNennungModel(
                id=nr["id"],
                nennungs_id=nr["nennungs_id"],
                paar_name=nr["paar_name"],
                min_partner_1=nr["min_partner_1"],
                min_partner_2=nr["min_partner_2"],
                klub=nr["klub"],
                turnier_id=nr["turnier_id"],
                turnier_db_id=nr["turnier_db_id"],
                klassen=klassen_map.get(nr["id"], [])
            )
            if nr["turnier_db_id"]:
                nennungen_by_tid.setdefault(nr["turnier_db_id"], []).append(model)
            if nr["turnier_id"]:
                nennungen_by_verband_id.setdefault(nr["turnier_id"], []).append(model)

        # Load all ergebnisse for these tournaments
        ergebnisse_query = f"""
            SELECT id, turnier_db_id, turnier_id, klasse_name, klasse_slug, platz, platz_sort,
                   total_paare, paar_name, startnr, klub, runde, bericht_url
            FROM turnier_ergebnisse
            WHERE turnier_db_id IN ({placeholders_id})
               OR (turnier_db_id IS NULL AND turnier_id IN ({placeholders_vid}))
            ORDER BY platz_sort ASC, id ASC;
        """
        ergebnisse_params = list(t_ids)
        if t_verband_ids:
            ergebnisse_params.extend(t_verband_ids)

        cursor.execute(ergebnisse_query, ergebnisse_params)
        ergebnis_rows = cursor.fetchall()

        ergebnisse_by_tid = {}
        ergebnisse_by_verband_id = {}
        for er in ergebnis_rows:
            emodel = TurnierErgebnisModel(
                id=er["id"],
                turnier_id=er["turnier_id"],
                turnier_db_id=er["turnier_db_id"],
                klasse_name=er["klasse_name"],
                klasse_slug=er["klasse_slug"],
                platz=er["platz"],
                platz_sort=er["platz_sort"],
                total_paare=er["total_paare"],
                paar_name=er["paar_name"],
                startnr=er["startnr"],
                klub=er["klub"],
                runde=er["runde"],
                bericht_url=er["bericht_url"]
            )
            if er["turnier_db_id"]:
                ergebnisse_by_tid.setdefault(er["turnier_db_id"], []).append(emodel)
            if er["turnier_id"]:
                ergebnisse_by_verband_id.setdefault(er["turnier_id"], []).append(emodel)

        # Load participant stats for these tournaments
        teilnehmer_query = f"""
            SELECT turnier_db_id, turnier_id,
                   COUNT(*) as anzahl_gesamt,
                   COUNT(DISTINCT paar_name) as anzahl_paare,
                   SUM(CASE WHEN is_utsc = 1 THEN 1 ELSE 0 END) as utsc_anzahl
            FROM turnier_teilnehmer
            WHERE turnier_db_id IN ({placeholders_id})
               OR (turnier_db_id IS NULL AND turnier_id IN ({placeholders_vid}))
            GROUP BY turnier_db_id, turnier_id;
        """
        cursor.execute(teilnehmer_query, ergebnisse_params)
        teilnehmer_rows = cursor.fetchall()

        teilnehmer_by_tid = {}
        teilnehmer_by_vid = {}
        for tr in teilnehmer_rows:
            info = {
                "anzahl": tr["anzahl_gesamt"],
                "paare": tr["anzahl_paare"],
                "utsc": tr["utsc_anzahl"] or 0
            }
            if tr["turnier_db_id"]:
                teilnehmer_by_tid[tr["turnier_db_id"]] = info
            if tr["turnier_id"]:
                teilnehmer_by_vid[tr["turnier_id"]] = info

        result: List[TurnierModel] = []
        for r in tournament_rows:
            tags = json.loads(r["tags"]) if r["tags"] else []
            links = json.loads(r["links"]) if r["links"] else {}

            paare = []
            seen_nids = set()

            # First match by turnier_db_id
            for p in nennungen_by_tid.get(r["id"], []):
                if p.nennungs_id not in seen_nids:
                    paare.append(p)
                    seen_nids.add(p.nennungs_id)

            # Fallback match by turnier_id
            if r["turnier_id"]:
                for p in nennungen_by_verband_id.get(r["turnier_id"], []):
                    if p.nennungs_id not in seen_nids:
                        paare.append(p)
                        seen_nids.add(p.nennungs_id)

            ergebnisse = ergebnisse_by_tid.get(r["id"]) or (ergebnisse_by_verband_id.get(r["turnier_id"]) if r["turnier_id"] else []) or []

            t_info = teilnehmer_by_tid.get(r["id"]) or (teilnehmer_by_vid.get(r["turnier_id"]) if r["turnier_id"] else None) or {}
            teilnehmer_anzahl = t_info.get("anzahl", 0)
            teilnehmer_utsc_anzahl = t_info.get("utsc", 0)
            teilnehmer_url = f"https://www.tanzsportverband.at/portal/nennungen/nennungen_liste_002.php?lang=DE&TASNr={r['turnier_id']}&sort=KLASSE&aktion=list" if r["turnier_id"] else None

            result.append(TurnierModel(
                id=r["id"],
                turnier_id=r["turnier_id"],
                datum=r["datum"],
                datum_sort=r["datum_sort"],
                titel=r["titel"],
                klub=r["klub"],
                bundesland=r["bundesland"],
                tags=tags,
                links=links,
                utsc_paare_anzahl=len(paare),
                utsc_paare=paare,
                ergebnisse_anzahl=len(ergebnisse),
                ergebnisse=ergebnisse,
                teilnehmer_anzahl=teilnehmer_anzahl,
                teilnehmer_utsc_anzahl=teilnehmer_utsc_anzahl,
                teilnehmer_url=teilnehmer_url
            ))

        return result

@router.get("/turniere/{turnier_db_id}/teilnehmer", response_model=TurnierTeilnehmerListResponse)
def get_turnier_teilnehmer(turnier_db_id: int):
    """Retrieve full participant list for a specific tournament grouped by class."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, turnier_id, datum, titel, klub, bundesland
            FROM turniere
            WHERE id = ? OR turnier_id = ?
            LIMIT 1;
        """, (turnier_db_id, turnier_db_id))
        t_row = cursor.fetchone()
        if not t_row:
            raise HTTPException(status_code=404, detail=f"Turnier mit ID {turnier_db_id} nicht gefunden.")

        t_db_id = t_row["id"]
        t_vid = t_row["turnier_id"]

        original_url = f"https://www.tanzsportverband.at/portal/nennungen/nennungen_liste_002.php?lang=DE&TASNr={t_vid}&sort=KLASSE&aktion=list" if t_vid else ""

        cursor.execute("""
            SELECT id, turnier_db_id, turnier_id, klasse, paar_name, klub, is_utsc, sort_order, updated_at
            FROM turnier_teilnehmer
            WHERE turnier_db_id = ? OR (turnier_id = ? AND turnier_id IS NOT NULL)
            ORDER BY sort_order ASC, id ASC;
        """, (t_db_id, t_vid))
        entries_rows = cursor.fetchall()

        # Group by class preserving class order
        classes_map = {}
        distinct_couples = set()
        utsc_count = 0
        last_updated = None

        for er in entries_rows:
            k = er["klasse"]
            if k not in classes_map:
                classes_map[k] = []

            is_utsc_bool = bool(er["is_utsc"])
            if is_utsc_bool:
                utsc_count += 1
            distinct_couples.add(er["paar_name"])
            if er["updated_at"]:
                last_updated = er["updated_at"]

            classes_map[k].append(TurnierTeilnehmerModel(
                id=er["id"],
                turnier_db_id=er["turnier_db_id"],
                turnier_id=er["turnier_id"],
                klasse=er["klasse"],
                paar_name=er["paar_name"],
                klub=er["klub"],
                is_utsc=is_utsc_bool,
                sort_order=er["sort_order"]
            ))

        klassen_models = []
        for k_name, p_list in classes_map.items():
            k_utsc = sum(1 for p in p_list if p.is_utsc)
            klassen_models.append(TurnierTeilnehmerKlasseModel(
                klasse=k_name,
                paare_anzahl=len(p_list),
                utsc_anzahl=k_utsc,
                paare=p_list
            ))

        return TurnierTeilnehmerListResponse(
            turnier_id=t_vid,
            turnier_db_id=t_db_id,
            titel=t_row["titel"],
            datum=t_row["datum"],
            klub=t_row["klub"],
            bundesland=t_row["bundesland"],
            original_url=original_url,
            total_anmeldungen=len(entries_rows),
            total_paare=len(distinct_couples),
            utsc_paare_anzahl=utsc_count,
            klassen_anzahl=len(klassen_models),
            klassen=klassen_models,
            last_updated=last_updated
        )

@router.get("/sync-status", response_model=List[SyncStatusModel])
def get_sync_status():
    """Retrieve execution status for all ingestion pipelines."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, last_run, added_count, updated_count, status, message FROM sync_status;")
        rows = cursor.fetchall()
        return [
            SyncStatusModel(
                key=r["key"],
                last_run=r["last_run"],
                added_count=r["added_count"],
                updated_count=r["updated_count"],
                status=r["status"],
                message=r["message"]
            )
            for r in rows
        ]

@router.get("/version")
def get_version():
    """Health check, system version info, and active club configuration."""
    st = storage_service.get_storage_status()
    return {
        "status": "healthy",
        "app_version": settings.APP_VERSION,
        "schema_version": "1.0",
        "backend": "FastAPI",
        "database": "SQLite (WAL)",
        "club_name": settings.CLUB_NAME,
        "club_short": settings.club_short_label,
        "setup_completed": st["setup_completed"],
        "storage_mode": st["storage_mode"],
        "lock_conflict": st["lock_conflict"],
        "lock_holder": st["lock_holder"],
        "read_only_cloud": st["read_only_cloud"],
    }


@router.get("/storage-setup", response_model=StorageConfigModel)
def get_public_storage_setup():
    """Retrieve storage setup status and detected cloud folders for the startup wizard."""
    return StorageConfigModel(**storage_service.get_storage_status())


@router.post("/storage-setup", response_model=StorageConfigModel)
def save_public_storage_setup(data: StorageConfigUpdateModel):
    """Save initial storage setup from the first-run wizard."""
    st = storage_service.get_storage_status()
    if st.get("setup_completed") and (settings.ADMIN_PASSWORD or "").strip():
        raise HTTPException(
            status_code=403,
            detail="Die Ersteinrichtung wurde bereits abgeschlossen. Bitte ändere den Speicherort im Admin-Center."
        )
    try:
        status_dict = storage_service.configure_storage(
            storage_mode=data.storage_mode,
            cloud_dir=data.cloud_dir,
            sync_imap=data.sync_imap,
            force_lock=data.force_lock,
        )
        return StorageConfigModel(**status_dict)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speicherort konnte nicht eingerichtet werden: {e}")


@router.post("/storage-setup/browse")
def browse_public_storage_folder():
    """Open native OS folder picker from the first-run setup dialog."""
    st = storage_service.get_storage_status()
    if st.get("setup_completed") and (settings.ADMIN_PASSWORD or "").strip():
        raise HTTPException(status_code=403, detail="Bitte im Admin-Center öffnen.")
    chosen = storage_service.open_native_folder_dialog(initial_dir=st.get("cloud_dir", ""))
    return {"selected_path": chosen}


@router.post("/storage-setup/resolve-lock", response_model=StorageConfigModel)
def resolve_public_storage_lock(data: StorageLockResolveModel):
    """Resolve an active multi-device lock conflict ('read_only' or 'takeover')."""
    status_dict = storage_service.resolve_lock_conflict(action=data.action)
    return StorageConfigModel(**status_dict)

