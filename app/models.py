from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class NennungsKlasseModel(BaseModel):
    id: Optional[int] = None
    datum: str
    klasse: str

class PaarNennungModel(BaseModel):
    id: Optional[int] = None
    nennungs_id: str
    paar_name: str
    min_partner_1: Optional[str] = None
    min_partner_2: Optional[str] = None
    klub: Optional[str] = None
    turnier_id: int
    turnier_db_id: Optional[int] = None
    klassen: List[NennungsKlasseModel] = Field(default_factory=list)

class TurnierErgebnisModel(BaseModel):
    id: Optional[int] = None
    turnier_id: int
    turnier_db_id: Optional[int] = None
    klasse_name: str
    klasse_slug: str
    platz: str
    platz_sort: Optional[int] = None
    total_paare: int = 0
    paar_name: str
    startnr: Optional[str] = None
    klub: Optional[str] = None
    runde: Optional[str] = None
    bericht_url: Optional[str] = None

class TurnierTeilnehmerModel(BaseModel):
    id: Optional[int] = None
    turnier_db_id: int
    turnier_id: int
    klasse: str
    paar_name: str
    klub: Optional[str] = None
    is_utsc: bool = False
    sort_order: int = 0

class TurnierTeilnehmerKlasseModel(BaseModel):
    klasse: str
    paare_anzahl: int
    utsc_anzahl: int
    paare: List[TurnierTeilnehmerModel] = Field(default_factory=list)

class TurnierTeilnehmerListResponse(BaseModel):
    turnier_id: Optional[int] = None
    turnier_db_id: int
    titel: str
    datum: str
    klub: Optional[str] = None
    bundesland: Optional[str] = None
    original_url: str
    total_anmeldungen: int = 0
    total_paare: int = 0
    utsc_paare_anzahl: int = 0
    klassen_anzahl: int = 0
    klassen: List[TurnierTeilnehmerKlasseModel] = Field(default_factory=list)
    last_updated: Optional[str] = None

class TurnierModel(BaseModel):
    id: int
    turnier_id: Optional[int] = None
    datum: str
    datum_sort: str
    titel: str
    klub: Optional[str] = None
    bundesland: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    links: Dict[str, str] = Field(default_factory=dict)
    utsc_paare_anzahl: int = 0
    utsc_paare: List[PaarNennungModel] = Field(default_factory=list)
    ergebnisse_anzahl: int = 0
    ergebnisse: List[TurnierErgebnisModel] = Field(default_factory=list)
    teilnehmer_anzahl: int = 0
    teilnehmer_utsc_anzahl: int = 0
    teilnehmer_url: Optional[str] = None

class SyncStatusModel(BaseModel):
    key: str
    last_run: Optional[str] = None
    added_count: int = 0
    updated_count: int = 0
    status: str = "idle"
    message: Optional[str] = None

class AdminStatusModel(BaseModel):
    status: str
    version: str
    server_time: str
    turniere_gesamt: int
    nennungen_gesamt: int
    klassen_gesamt: int
    ergebnisse_gesamt: int = 0
    teilnehmer_gesamt: int = 0
    running_jobs: List[str]
    next_runs: Dict[str, Optional[str]]
    sync_status: Dict[str, SyncStatusModel]

class ChangelogEntry(BaseModel):
    version: str
    date: str
    changes: List[str]

class ImapConfigModel(BaseModel):
    imap_enabled: bool
    imap_server: str
    imap_port: int = 993
    imap_user: str
    has_password: bool = False
    imap_mailbox: str = "INBOX"
    imap_fetch_interval_minutes: int = 15
    imap_allowed_senders: str
    imap_mock: bool = False

class ImapConfigUpdateModel(BaseModel):
    imap_enabled: bool
    imap_server: str
    imap_port: int = 993
    imap_user: str
    imap_password: Optional[str] = None
    imap_mailbox: str = "INBOX"
    imap_fetch_interval_minutes: int = 15
    imap_allowed_senders: str
    imap_mock: bool = False

class ClubConfigModel(BaseModel):
    club_name: str
    club_short: str
    club_keywords: str = ""
    effective_tokens: List[str] = Field(default_factory=list)

class ClubConfigUpdateModel(BaseModel):
    club_name: str
    club_short: str = ""
    club_keywords: str = ""

class CloudProviderModel(BaseModel):
    id: str
    name: str
    base_path: str
    suggested_path: str
    existing_db: bool = False

class StorageConfigModel(BaseModel):
    setup_completed: bool = False
    storage_mode: str = "local"
    cloud_dir: str = ""
    sync_imap: bool = False
    local_db_path: str = ""
    cloud_db_exists: bool = False
    cloud_config_exists: bool = False
    last_sync: Optional[str] = None
    last_error: Optional[str] = None
    lock_conflict: bool = False
    lock_holder: Optional[Dict[str, Any]] = None
    read_only_cloud: bool = False
    detected_providers: List[CloudProviderModel] = Field(default_factory=list)

class StorageConfigUpdateModel(BaseModel):
    storage_mode: str = "local"
    cloud_dir: str = ""
    sync_imap: bool = False
    force_lock: bool = False

class StorageLockResolveModel(BaseModel):
    action: str = "read_only"  # "read_only" or "takeover"



