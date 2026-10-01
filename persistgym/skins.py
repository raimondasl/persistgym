"""Surface stories ("skins"). A skin supplies nouns only; the task structure is identical.

All agent-facing sentences are built from the fixed frames in `render.py`, so the oracle and
the audits can parse them. Entity names are upper-case single words; they are reserved per
template and never appear in log filler.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skin:
    name: str
    facility: str
    sites: tuple[str, ...]
    kind: str  # entity kind, lower case, one word
    entities: tuple[str, ...]
    quantity: str  # the target quantity, e.g. "loading bay"
    components: tuple[str, str, str]  # base, offset, shift (clue names)
    sources: tuple[str, str, str]  # record sources for clue 0/1/2 (observed uses sources[0])
    need_verb: str
    route_noun: str
    route_tags: tuple[str, ...]
    sensor_metrics: tuple[tuple[str, str], ...]  # (metric, unit); readings are 4-digit
    broadcast_senders: tuple[str, ...]
    services: tuple[str, ...]  # log filler service names
    null_records: tuple[str, ...]  # withheld-control sentences, "{Kind} {E} ..."


SKINS: dict[str, Skin] = {
    "warehouse": Skin(
        name="warehouse",
        facility="dispatch console",
        sites=("the Northgate distribution centre", "the Harbourside fulfilment hub",
               "the Ridgeway cross-dock"),
        kind="shipment",
        entities=("ORION", "VEGA", "RIGEL", "ALTAIR", "DENEB", "SIRIUS", "CAPELLA", "POLLUX",
                  "ANTARES", "ARCTURUS", "BETELGEUSE", "CANOPUS", "PROCYON", "SPICA",
                  "REGULUS", "MIRA", "ALNILAM", "MIZAR", "ALCOR", "CASTOR", "ACHERNAR",
                  "HADAR", "SHAULA", "ELNATH", "ALHENA", "MENKAR", "NUNKI", "SABIK"),
        quantity="loading bay",
        components=("base bay", "priority offset", "lane shift"),
        sources=("Dispatch memo", "Priority desk note", "Yard notice"),
        need_verb="assign",
        route_noun="Ticket",
        route_tags=("billing", "customs", "inventory", "returns", "carrier", "packaging"),
        sensor_metrics=(("conveyor load", "kg"), ("dock pressure", "Pa"),
                        ("pallet weight", "kg"), ("belt speed", "mm/s")),
        broadcast_senders=("shift lead", "safety office", "yard control"),
        services=("wms-api", "scanner-gw", "conveyor-ctl", "label-svc", "route-planner",
                  "inv-sync", "auth-svc", "metrics-agent"),
        null_records=("{Kind} {E} is on today's manifest.",
                      "{Kind} {E} passed the weight check.",
                      "{Kind} {E} has its paperwork complete."),
    ),
    "biobank": Skin(
        name="biobank",
        facility="sample-tracking console",
        sites=("the Eastfield biobank", "the Linden clinical lab", "the Moorgate core facility"),
        kind="sample",
        entities=("ALDER", "BIRCH", "CEDAR", "ELM", "HAZEL", "HOLLY", "JUNIPER", "LARCH",
                  "MAPLE", "OAK", "PINE", "ROWAN", "SPRUCE", "WILLOW", "YEW", "ASPEN",
                  "BEECH", "CYPRESS", "FIR", "HAWTHORN", "LINDEN", "POPLAR", "SEQUOIA",
                  "SYCAMORE", "TAMARACK", "HEMLOCK", "MAGNOLIA", "ACACIA"),
        quantity="freezer slot",
        components=("rack slot", "shelf offset", "overflow shift"),
        sources=("Intake memo", "Storage desk note", "Freezer notice"),
        need_verb="store",
        route_noun="Request",
        route_tags=("sequencing", "imaging", "assay", "billing", "shipping", "consent"),
        sensor_metrics=(("compressor current", "mA"), ("door cycle count", "cycles"),
                        ("LN2 level", "mm"), ("fan speed", "rpm")),
        broadcast_senders=("lab manager", "biosafety office", "facilities"),
        services=("lims-api", "barcode-gw", "freezer-mon", "label-svc", "sched-svc",
                  "inv-sync", "auth-svc", "metrics-agent"),
        null_records=("{Kind} {E} has been logged at intake.",
                      "{Kind} {E} passed the barcode check.",
                      "{Kind} {E} has its consent form on file."),
    ),
    "datacenter": Skin(
        name="datacenter",
        facility="hardware-ops console",
        sites=("the Westbrook data hall", "the Kestrel colocation site", "the Fenwick edge site"),
        kind="server",
        entities=("ATLAS", "BOREAS", "CALYPSO", "DAPHNE", "EOS", "GAIA", "HELIOS", "IRIS",
                  "JANUS", "KRONOS", "LETO", "METIS", "NYX", "OCEANUS", "PALLAS", "RHEA",
                  "SELENE", "TETHYS", "THEIA", "URANIA", "ZEPHYR", "PHOEBE", "HYPERION",
                  "CRIUS", "COEUS", "THEMIS", "MNEMOSYNE", "ASTRAEA"),
        quantity="rack position",
        components=("row base", "cage offset", "power shift"),
        sources=("Install memo", "Capacity desk note", "Power notice"),
        need_verb="mount",
        route_noun="Ticket",
        route_tags=("network", "storage", "cooling", "power", "security", "procurement"),
        sensor_metrics=(("inlet airflow", "cfm"), ("PDU draw", "W"), ("fan speed", "rpm"),
                        ("chassis count", "units")),
        broadcast_senders=("site lead", "change board", "NOC"),
        services=("dcim-api", "ipmi-gw", "pdu-ctl", "asset-svc", "netbox-sync", "auth-svc",
                  "metrics-agent", "cron"),
        null_records=("{Kind} {E} has been received at the loading dock.",
                      "{Kind} {E} passed burn-in.",
                      "{Kind} {E} has its asset tag recorded."),
    ),
    "archive": Skin(
        name="archive",
        facility="records-retrieval console",
        sites=("the County records archive", "the Harlow university archive",
               "the Marsh library annex"),
        kind="box",
        entities=("AMAZON", "DANUBE", "GANGES", "INDUS", "JORDAN", "LOIRE", "MEKONG",
                  "NIGER", "ORINOCO", "RHINE", "SEVERN", "TAGUS", "TIBER", "VOLGA", "YUKON",
                  "ZAMBEZI", "ELBE", "ODER", "SHANNON", "TRENT", "CONGO", "DOURO", "EBRO",
                  "MURRAY", "OHIO", "PLATTE", "RHONE", "SEINE"),
        quantity="shelf number",
        components=("aisle base", "bay offset", "annex shift"),
        sources=("Accession memo", "Reading-room note", "Stacks notice"),
        need_verb="shelve",
        route_noun="Request",
        route_tags=("conservation", "digitising", "loans", "reference", "copyright", "billing"),
        sensor_metrics=(("air exchange", "l/min"), ("lux exposure", "lux"),
                        ("CO2 reading", "ppm"), ("dust count", "particles")),
        broadcast_senders=("head archivist", "conservation office", "facilities"),
        services=("catalog-api", "scan-gw", "hvac-ctl", "label-svc", "search-idx", "auth-svc",
                  "metrics-agent", "cron"),
        null_records=("{Kind} {E} has been accessioned.",
                      "{Kind} {E} passed the condition check.",
                      "{Kind} {E} has its finding aid on file."),
    ),
    "depot": Skin(
        name="depot",
        facility="fleet-depot console",
        sites=("the Southmere bus depot", "the Castlegate fleet yard", "the Brookside garage"),
        kind="vehicle",
        entities=("ALBATROSS", "BITTERN", "CORMORANT", "DUNLIN", "EGRET", "FALCON",
                  "GANNET", "HERON", "IBIS", "KESTREL", "LAPWING", "MERLIN", "NIGHTJAR",
                  "OSPREY", "PETREL", "QUAIL", "RAVEN", "SANDPIPER", "TERN", "WAGTAIL",
                  "WREN", "SWIFT", "PLOVER", "CURLEW", "GOSHAWK", "PUFFIN", "SKYLARK",
                  "STARLING"),
        quantity="parking stall",
        components=("lot base", "charger offset", "rota shift"),
        sources=("Fleet memo", "Charging desk note", "Rota notice"),
        need_verb="park",
        route_noun="Work order",
        route_tags=("brakes", "tyres", "electrics", "bodywork", "cleaning", "telematics"),
        sensor_metrics=(("battery voltage", "mV"), ("charger current", "mA"),
                        ("tyre pressure", "hPa"), ("odometer delta", "m")),
        broadcast_senders=("depot manager", "safety office", "control room"),
        services=("fleet-api", "telematics-gw", "charger-ctl", "rota-svc", "parts-sync",
                  "auth-svc", "metrics-agent", "cron"),
        null_records=("{Kind} {E} has returned to the depot.",
                      "{Kind} {E} passed the daily walk-round check.",
                      "{Kind} {E} has its defect sheet signed."),
    ),
}


def get_skin(name: str) -> Skin:
    try:
        return SKINS[name]
    except KeyError as e:
        raise ValueError(f"unknown skin {name!r}; known: {sorted(SKINS)}") from e
